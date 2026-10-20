"""
panel_engine.py -- serve the multi-virus (ProteinGym Growth) model.

This is the second model. quantum_engine.py serves the SARS-CoV-2 specialist
(weights.npz, 4 features incl. ace2_distance). This serves the cross-virus
generalist (weights_panel.npz, 6 features incl. burial) over the 17 proteins
whose AlphaFold structure numbering was verified against the assay wildtype.

WHY THIS IS A SEPARATE ENGINE, NOT A FLAG
-----------------------------------------
The two models differ in three ways that all have to be right at once:
  * feature set: panel uses [blosum62, wt_volume, delta_volume, wt_hydropathy,
    delta_hydropathy, burial] -- NO ace2_distance (meaningless off SARS-CoV-2),
    PLUS burial (meaningless without a structure).
  * blosum62 clamp: the panel model was trained with the LEGACY range (-4, 11).
    mutation_features.RANGES now ships (-4, 3). Scoring the panel model with the
    wrong clamp remaps every blosum angle and silently corrupts the output, so
    the clamp is read from metrics_panel.json, not from the live RANGES.
  * burial: supplied per (protein, site) from burial.json, which only covers
    the 17 verified proteins. There is no burial for an arbitrary protein, so
    this engine scores ONLY catalogued proteins at covered sites.

The quantum circuit itself is identical to training: it is built by the same
circuit.make_qnode, with geometry read back from the weights file. So the
forward pass cannot drift from what was trained; only featurisation is new
code, and that is covered by test_panel_parity.py.
"""

from __future__ import annotations

import json
import os

import numpy as np

import mutation_features as mf
from circuit import make_qnode, logits, n_readout_params, qubits_needed

HERE = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_PATH = os.path.join(HERE, "weights_panel.npz")
METRICS_PATH = os.path.join(HERE, "metrics_panel.json")
CATALOG_PATH = os.path.join(HERE, "panel_catalog.json")
BURIAL_PATH = os.path.join(HERE, "burial.json")
BURIAL_RADIUS = "cn10"       # the radius the panel was trained on
SHOTS = int(os.getenv("QVIRA_SHOTS", "2048"))
BACKEND = os.getenv("QVIRA_BACKEND", "default.qubit")


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


class PanelEngine:
    def __init__(self):
        self.ok = False
        self.reason = "not loaded"
        self.weights = None
        self.readout = None
        self.readout_kind = "probs"
        self.encoding = "dense"
        self.axes = ("Y", "Z")
        self.feature_cols = (4, 6, 2, 5, 0, 9)
        self.n_qubits = 3
        self.blosum_clamp = (-4.0, 11.0)
        self.catalog = {}
        self.burial = {}
        self.metadata = {}
        self._qnode = None
        self._qnode_probs = None
        try:
            self.load()
            self.ok = True
            self.reason = "ok"
        except Exception as exc:                      # noqa: BLE001
            # The SARS-CoV-2 model must still serve even if the panel is absent
            # or malformed, so loading never raises into the app.
            self.reason = f"{type(exc).__name__}: {exc}"

    def load(self) -> None:
        for p in (WEIGHTS_PATH, CATALOG_PATH, BURIAL_PATH):
            if not os.path.exists(p):
                raise FileNotFoundError(os.path.basename(p))

        d = np.load(WEIGHTS_PATH, allow_pickle=True)
        self.weights = np.asarray(d["weights"], dtype=float)
        self.readout = np.asarray(d["readout"], dtype=float).ravel()
        self.readout_kind = (str(d["readout_kind"].item())
                             if "readout_kind" in d else "probs")
        self.encoding = str(d["encoding"].item()) if "encoding" in d else "dense"
        self.axes = tuple(str(d["axes"].item()).split(",")) if "axes" in d \
            else ("Y", "Z")
        self.feature_cols = tuple(int(c) for c in
                                  np.asarray(d["feature_cols"]).ravel()) \
            if "feature_cols" in d else (4, 6, 2, 5, 0, 9)
        self.n_qubits = int(self.weights.shape[1])
        if "metadata" in d:
            self.metadata = dict(d["metadata"].item())

        # The blosum clamp the panel was TRAINED with. This is the landmine:
        # it is (-4, 11) for the shipped panel model but (-4, 3) in the live
        # featuriser, so it must come from the model's own metrics.
        self.blosum_clamp = (-4.0, 11.0)
        if os.path.exists(METRICS_PATH):
            m = json.load(open(METRICS_PATH))
            bc = m.get("blosum62_clamp") or m.get("vqc", {}).get("blosum62_clamp")
            if bc:
                self.blosum_clamp = (float(bc[0]), float(bc[1]))

        # geometry consistency, same guard as the SARS engine
        need = qubits_needed(len(self.feature_cols), self.encoding, self.axes)
        if self.n_qubits != need:
            raise ValueError(
                f"panel weights have {self.n_qubits} qubits but "
                f"{len(self.feature_cols)} features under {self.encoding}/"
                f"{self.axes} need {need}")
        exp = n_readout_params(self.n_qubits, self.readout_kind)
        if self.readout.size != exp:
            raise ValueError(f"panel readout size {self.readout.size} != {exp}")

        self.catalog = json.load(open(CATALOG_PATH))
        self.burial = json.load(open(BURIAL_PATH))

        self._qnode = make_qnode(len(self.feature_cols), self.n_qubits,
                                 self.readout_kind, self.encoding, self.axes,
                                 shots=None, backend=BACKEND)
        self._qnode_probs = make_qnode(len(self.feature_cols), self.n_qubits,
                                       "probs", self.encoding, self.axes,
                                       shots=None, backend=BACKEND)

    # ---- featurisation -------------------------------------------------
    def _scale_one(self, col: int, value: float) -> float:
        lo, hi = ((self.blosum_clamp) if col == 4 else mf.RANGES[col])
        import math
        return (min(max(value, lo), hi) - lo) / (hi - lo) * math.pi

    def featurise(self, wt: str, mut: str, site: int, burial: float):
        """Build the scaled angle vector in feature_cols order.

        Mirrors train_vqc.load_panel + _scale_block exactly: raw_descriptors
        supplies indices 0-8, burial is index 9, each column scaled by its
        range (blosum by the trained clamp). rel_pos and site do not affect any
        selected column, so they are passed as inert values.
        """
        raw = mf.raw_descriptors(wt, mut, 0.0, site=site)  # indices 0-8
        full = list(raw) + [float(burial)]                 # index 9 = burial
        return [self._scale_one(c, full[c]) for c in self.feature_cols]

    # ---- scoring -------------------------------------------------------
    def wildtype_at(self, protein: str, site: int):
        return self.catalog.get(protein, {}).get("sites", {}).get(str(site))

    def burial_at(self, protein: str, site: int):
        rec = self.burial.get(protein, {}).get(str(site))
        return None if rec is None else float(rec[BURIAL_RADIUS])

    def score(self, protein: str, site: int, mut: str) -> dict:
        from pennylane import numpy as pnp
        if not self.ok:
            raise RuntimeError(f"panel model unavailable ({self.reason})")
        if protein not in self.catalog:
            raise KeyError(f"unknown protein {protein!r}")
        wt = self.wildtype_at(protein, site)
        if wt is None:
            raise KeyError(f"site {site} not covered for {protein}")
        bur = self.burial_at(protein, site)
        if bur is None:
            raise KeyError(f"no burial for {protein} site {site}")
        mut = mut.upper()
        if mut not in mf.VALID:
            raise ValueError(f"non-standard residue {mut!r}")
        if mut == wt:
            raise ValueError("mutant equals wildtype -- no substitution")

        ang = np.asarray(self.featurise(wt, mut, site, bur), dtype=float)
        raw = self._qnode(ang, pnp.array(self.weights, requires_grad=False))
        logit = float(logits(raw, pnp.array(self.readout, requires_grad=False),
                             self.readout_kind))
        p = float(_sigmoid(logit))
        return {
            "protein": protein,
            "virus": self.catalog[protein]["virus"],
            "mutation": f"{wt}{site}{mut}",
            "wildtype": wt, "site": int(site), "mutant": mut,
            "burial_cn10": bur,
            "score": round(p, 4),
            "interpretation": ("higher = more likely to retain function "
                               "(worth characterising first)"),
            "n_qubits": self.n_qubits,
            "n_parameters": int(self.weights.size + self.readout.size),
        }

    def distribution(self, protein: str, site: int, mut: str) -> list[dict]:
        from pennylane import numpy as pnp
        wt = self.wildtype_at(protein, site)
        bur = self.burial_at(protein, site)
        ang = np.asarray(self.featurise(wt, mut, site, bur), dtype=float)
        probs = np.asarray(
            self._qnode_probs(ang, pnp.array(self.weights, requires_grad=False)),
            dtype=float)
        w = self.n_qubits
        return [{"state": f"|{i:0{w}b}>", "probability": round(float(x) * 100, 3)}
                for i, x in enumerate(probs)]

    def list_viruses(self) -> list[dict]:
        """Catalogue for the UI dropdowns: virus -> proteins -> sites(+wt)."""
        out = {}
        for dms, v in self.catalog.items():
            out.setdefault(v["virus"], []).append({
                "id": dms, "display": v["display"], "n_sites": v["n_sites"],
            })
        return [{"virus": k, "assays": sorted(val, key=lambda a: a["display"])}
                for k, val in sorted(out.items())]

    def sites_for(self, protein: str) -> list[dict]:
        s = self.catalog.get(protein, {}).get("sites", {})
        return [{"site": int(k), "wildtype": a}
                for k, a in sorted(s.items(), key=lambda kv: int(kv[0]))]


panel_engine = PanelEngine()
