"""
Variational quantum circuit for Q-VIRA -- inference side.

The weights are LOADED FROM DISK (weights.npz, produced by train_vqc.py). If
that file is missing the engine reports trained=False and the API refuses to
dress the output up as a prediction. There is no silent fallback to random
weights.

The ansatz itself now lives in circuit.py and is imported by BOTH this file and
train_vqc.py, so the circuit that was trained and the circuit that is served
cannot drift apart. It used to be written out twice.

READOUT
-------
weights.npz carries a `readout_kind` field:

  probs      p = sigmoid(sum_k w_k P(k) + b) over all 2^n basis outcomes.
             The current model. Uses the whole state the entangling layers
             built, rather than one qubit of four.

  single_z   p = sigmoid(w <Z_0> + b). The original two-parameter readout.

Files saved before readout_kind existed have no such field; they are loaded as
single_z, so an old weights.npz keeps working.

Backends
--------
  default.qubit  analytic statevector, no shot noise (default; fast)
  shots=N        sampled, so we can report a real error bar
  qiskit.aer     set QVIRA_BACKEND=qiskit.aer if pennylane-qiskit is installed
"""

from __future__ import annotations

import os

import numpy as np

from circuit import (make_qnode, logits, n_readout_params, qubits_needed,
                     DEFAULT_AXES)
from mutation_features import N_FEATURES, SELECTED, NAMES

# Circuit width is NO LONGER the same as the feature count. Under `angle`
# encoding they coincide; under `dense` several features share a wire. Both the
# encoding and the width are read back from weights.npz rather than assumed,
# because serving a different geometry than was trained produces plausible
# numbers that are silently wrong.
WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "weights.npz")
SHOTS = int(os.getenv("QVIRA_SHOTS", "2048"))
BACKEND = os.getenv("QVIRA_BACKEND", "default.qubit")


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def _expectation_z0(probs: np.ndarray, n_qubits: int) -> float:
    """<Z_0> recovered from the basis distribution.

    qml.probs(wires=range(n)) indexes states with wire 0 as the MOST
    significant bit, so state k has wire 0 set when (k >> (n-1)) & 1.
    Z eigenvalue is +1 for |0> and -1 for |1>.
    """
    k = np.arange(len(probs))
    sign = np.where((k >> (n_qubits - 1)) & 1, -1.0, 1.0)
    return float(np.sum(probs * sign))


class Engine:
    """Holds the trained parameters and turns features into a score."""

    def __init__(self):
        self.weights = None
        self.readout = None
        self.readout_kind = "probs"
        self.encoding = "angle"
        self.axes = DEFAULT_AXES
        self.n_features = N_FEATURES
        self.n_qubits = N_FEATURES
        self.metadata = {}
        self._qnode_exact = None
        self._qnode_shots = None
        self._qnode_probs = None
        self.load()

    @staticmethod
    def _str(data, key, default):
        """Read a 0-d numpy string array back as a plain str."""
        if key not in data:
            return default
        v = data[key]
        return str(v.item() if hasattr(v, "item") else v)

    # -- loading ---------------------------------------------------------
    def load(self) -> bool:
        if not os.path.exists(WEIGHTS_PATH):
            return False
        data = np.load(WEIGHTS_PATH, allow_pickle=True)

        w = np.asarray(data["weights"], dtype=float)
        if w.ndim != 3 or w.shape[2] != 3:
            raise ValueError(f"weights.npz has shape {w.shape}, expected (L, n_qubits, 3)")

        # Geometry, read back rather than assumed. Files predating dense
        # encoding have none of these fields and are angle-encoded.
        self.encoding = self._str(data, "encoding", "angle")
        self.axes = tuple(self._str(data, "axes", ",".join(DEFAULT_AXES)).split(","))
        self.n_features = int(data["n_features"]) if "n_features" in data \
            else int(w.shape[1])

        if self.n_features != N_FEATURES:
            raise ValueError(
                f"weights.npz was trained on {self.n_features} features but "
                f"the featuriser now produces {N_FEATURES} (SELECTED changed). "
                f"Retrain rather than serving a mismatched model."
            )

        # WHICH features, not just how many. A 6-feature panel model and a
        # 6-feature SARS-CoV-2 model have identical counts, widths and
        # encodings; only the column indices tell them apart.
        if "feature_cols" in data:
            cols = tuple(int(c) for c in np.asarray(data["feature_cols"]).ravel())
            if cols != tuple(SELECTED):
                raise ValueError(
                    f"weights.npz was trained on descriptor columns {cols} "
                    f"({[NAMES[c] for c in cols]}) but SELECTED is "
                    f"{tuple(SELECTED)} ({[NAMES[c] for c in SELECTED]}). "
                    f"These have the same feature COUNT, so the count check "
                    f"below cannot catch it -- serving this model would score "
                    f"mutations with the wrong descriptors. Load the matching "
                    f"weights file or retrain."
                )
            self.feature_cols = cols
        else:
            self.feature_cols = tuple(SELECTED)

        expected_q = qubits_needed(self.n_features, self.encoding, self.axes)
        if w.shape[1] != expected_q:
            raise ValueError(
                f"weights.npz has {w.shape[1]} qubits but {self.n_features} "
                f"features under encoding={self.encoding!r} axes={self.axes} "
                f"need {expected_q}. Retrain."
            )
        self.n_qubits = int(w.shape[1])
        self.weights = w

        # readout_kind may be absent (files predating the multi-observable
        # readout) or stored as a 0-d numpy string array.
        self.readout_kind = self._str(data, "readout_kind", "single_z")

        if "readout" in data:
            self.readout = np.asarray(data["readout"], dtype=float).ravel()
        else:
            self.readout = np.array([1.0, 0.0])
            self.readout_kind = "single_z"

        expected = n_readout_params(self.n_qubits, self.readout_kind)
        if self.readout.size != expected:
            raise ValueError(
                f"weights.npz has {self.readout.size} readout parameters but "
                f"readout_kind={self.readout_kind!r} at {self.n_qubits} qubits "
                f"needs {expected}. The file and the featuriser disagree -- "
                f"retrain rather than serving a mismatched model."
            )

        if "metadata" in data:
            self.metadata = dict(data["metadata"].item())

        # Build the QNodes once. The probs node is used for the state-
        # distribution panel regardless of which readout is active.
        geom = dict(n_features=self.n_features, n_qubits=self.n_qubits,
                    encoding=self.encoding, axes=self.axes, backend=BACKEND)
        self._qnode_exact = make_qnode(readout_kind=self.readout_kind,
                                       shots=None, **geom)
        self._qnode_shots = make_qnode(readout_kind=self.readout_kind,
                                       shots=SHOTS, **geom)
        self._qnode_probs = make_qnode(readout_kind="probs",
                                       shots=None, **geom)
        return True

    @property
    def is_trained(self) -> bool:
        return self.weights is not None

    @property
    def n_parameters(self) -> int:
        """Circuit parameters plus readout parameters.

        main.py used to compute `weights.size + 2`, hardcoding the old
        two-parameter readout. Use this instead."""
        if not self.is_trained:
            return 0
        return int(self.weights.size + self.readout.size)

    # -- scoring ---------------------------------------------------------
    def _proba_from_raw(self, raw) -> float:
        return float(_sigmoid(float(logits(raw, self.readout, self.readout_kind))))

    def score(self, features, with_error_bar: bool = True) -> dict:
        """Return the normalised threat score in [0, 1]."""
        if not self.is_trained:
            raise RuntimeError(
                "No trained weights found. Run `python train_vqc.py` first. "
                "Q-VIRA will not emit a score from untrained parameters."
            )

        f = np.asarray(features, dtype=float)
        raw = np.asarray(self._qnode_exact(f, self.weights), dtype=float)

        if self.readout_kind == "probs":
            z0 = _expectation_z0(raw, self.n_qubits)
        else:
            z0 = float(raw)

        out = {
            "threat_score": self._proba_from_raw(raw),
            "expectation_z": z0,
            "trained": True,
            "n_features": self.n_features,
            "n_qubits": self.n_qubits,
            "n_layers": int(self.weights.shape[0]),
            "readout": self.readout_kind,
            "encoding": self.encoding,
            "axes": list(self.axes) if self.encoding == "dense" else None,
            "n_circuit_parameters": int(self.weights.size),
            "n_readout_parameters": int(self.readout.size),
            "n_parameters": self.n_parameters,
            "ansatz": "data-reuploading-StronglyEntanglingLayers",
            "backend": BACKEND,
        }

        if with_error_bar:
            sampled_raw = np.asarray(self._qnode_shots(f, self.weights),
                                     dtype=float)
            p = self._proba_from_raw(sampled_raw)

            if self.readout_kind == "probs":
                # The logit is a linear functional of a multinomial sample,
                # L = sum_k w_k p_k. Its exact sampling variance over N shots is
                #   Var(L) = (1/N) [ sum_k w_k^2 p_k  -  (sum_k w_k p_k)^2 ]
                # which accounts for the covariance between outcome counts.
                w = self.readout[:-1]
                m1 = float(np.sum(w * sampled_raw))
                m2 = float(np.sum(w * w * sampled_raw))
                se_logit = (max(0.0, m2 - m1 * m1) / SHOTS) ** 0.5
            else:
                # +/-1 valued observable: Var = 1 - <Z>^2.
                var = max(0.0, 1.0 - float(sampled_raw) ** 2)
                se_logit = abs(self.readout[0]) * (var / SHOTS) ** 0.5

            out["shots"] = SHOTS
            out["threat_score_sampled"] = p
            # Propagate through the sigmoid: dp/dL = p(1-p).
            out["threat_score_stderr"] = float(p * (1 - p) * se_logit)

        return out

    def distribution(self, features) -> list[dict]:
        """Basis-state probabilities for the VQC tab.

        With the probs readout these are not a side-show any more: they are
        exactly the numbers the readout consumes, so the panel is now showing
        the model's actual input rather than an illustration of it.
        """
        if not self.is_trained:
            raise RuntimeError("No trained weights found.")
        probs = np.asarray(
            self._qnode_probs(np.asarray(features, dtype=float), self.weights),
            dtype=float,
        )
        width = self.n_qubits
        return [
            {"state": f"|{i:0{width}b}>", "probability": round(float(p) * 100, 3)}
            for i, p in enumerate(probs)
        ]


engine = Engine()
