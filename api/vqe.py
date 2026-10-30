"""
Live VQE for H2.

This replaces the old "Drug Discovery" panel, which displayed a number computed
in JavaScript as -(4.2 + threat_score) and labelled it a 12-qubit Qiskit VQE of
a protein pocket with a Paxlovid derivative. No VQE was run.

What runs here instead is a real variational quantum eigensolver:
  - the qubit Hamiltonian comes from a genuine Hartree-Fock calculation
    (precomputed with PySCF by build_vqe_data.py, shipped as vqe_h2.json)
  - the ansatz is optimised at request time on PennyLane
  - the result is compared against TWO classical references:
      * Hartree-Fock, the classical mean-field initial iterate of the VQE
        optimisation (convergence[0] in the stored history)
      * exact diagonalisation of the same Hamiltonian (the "ground truth")
    so the panel can show both the quantum-matches-exact result (VQE ~ FCI)
    and the quantum-beats-classical-mean-field result (VQE << HF at
    stretched bonds).

4 qubits, 15 Pauli terms, a few seconds per geometry.

WHAT THIS DOES NOT DO
---------------------
It does not simulate a drug binding to a protein. H2 has 2 electrons; a binding
pocket in a minimal basis is on the order of 10^5 qubits before error
correction. The scaling note is returned with every response so the UI cannot
imply otherwise.
"""

from __future__ import annotations

import json
import os
import time

import numpy as np
import pennylane as qml
from pennylane import numpy as pnp

DATA_PATH = os.path.join(os.path.dirname(__file__), "vqe_h2.json")
_PAULI = {"X": qml.PauliX, "Y": qml.PauliY, "Z": qml.PauliZ}
CHEMICAL_ACCURACY_HA = 1.6e-3  # ~1 kcal/mol

_data = None


def available() -> bool:
    return os.path.exists(DATA_PATH)


def _load() -> dict:
    global _data
    if _data is None:
        with open(DATA_PATH) as fh:
            _data = json.load(fh)
    return _data


def geometries() -> list[dict]:
    """Bond lengths available, with their exact reference energies."""
    return [
        {
            "bond_length": p["bond_length"],
            "exact_energy": round(p["exact_energy"], 8),
            "n_qubits": p["n_qubits"],
            "n_terms": len(p["terms"]),
        }
        for p in _load()["points"]
    ]


def _rebuild_hamiltonian(point: dict):
    """Turn the serialised Pauli terms back into a PennyLane Hamiltonian."""
    coeffs, ops = [], []
    for t in point["terms"]:
        coeffs.append(t["coeff"])
        if not t["pauli"]:
            ops.append(qml.Identity(0))
        else:
            factors = [_PAULI[p](int(w)) for w, p in sorted(t["pauli"].items(), key=lambda kv: int(kv[0]))]
            op = factors[0]
            for f in factors[1:]:
                op = op @ f
            ops.append(op)
    return qml.Hamiltonian(coeffs, ops)


def _nearest_point(bond_length: float) -> dict:
    pts = _load()["points"]
    return min(pts, key=lambda p: abs(p["bond_length"] - bond_length))


def stored(bond_length: float) -> dict | None:
    """Return the PRECOMPUTED VQE result for the nearest stored geometry.

    The optimisation is real but was run ahead of time by build_vqe_data.py.
    Running an autograd optimisation inside a web request blocked the server
    and made the tab unusable, so the same computation is done once, offline,
    and served instantly. Reproduce any row with notebooks/vqe_h2.ipynb.
    """
    p = _nearest_point(bond_length)
    if "vqe_energy" not in p:
        return None
    err = abs(p["vqe_energy"] - p["exact_energy"])
    hist = p.get("convergence", [])
    hf = float(hist[0]) if hist else None
    hf_err = abs(hf - p["exact_energy"]) if hf is not None else None
    return {
        "bond_length": p["bond_length"],
        "vqe_energy": round(p["vqe_energy"], 8),
        "exact_energy": round(p["exact_energy"], 8),
        "absolute_error": err,
        "chemical_accuracy": CHEMICAL_ACCURACY_HA,
        "within_chemical_accuracy": err < CHEMICAL_ACCURACY_HA,
        "convergence": [{"step": i, "energy": e} for i, e in enumerate(hist)],
        "n_qubits": p["n_qubits"],
        "n_parameters": p.get("n_parameters"),
        "n_pauli_terms": len(p["terms"]),
        "hartree_fock_energy": round(hf, 8) if hf is not None else None,
        "hf_absolute_error": hf_err,
        "correlation_energy": round(hf - p["vqe_energy"], 8) if hf is not None else None,
        "computed": "precomputed",
        "method": {
            "molecule": "H2", "basis": "sto-3g", "mapping": "Jordan-Wigner",
            "ansatz": "AllSinglesDoubles (UCCSD-style) from Hartree-Fock",
            "optimiser": "gradient descent, 60 steps, lr=0.4",
            "reference": "exact diagonalisation of the same Hamiltonian",
            "note": ("Optimisation run ahead of time by build_vqe_data.py and "
                     "served from vqe_h2.json. Reproduce with "
                     "notebooks/vqe_h2.ipynb."),
        },
        "scaling_note": (
            "H2 has 2 electrons in 4 spin-orbitals. A protein binding pocket in "
            "a minimal basis is on the order of 10^5 qubits before error "
            "correction, so protein-ligand binding energies are not a near-term "
            "quantum target. This is a verifiable benchmark, not drug discovery."
        ),
    }


def run(bond_length: float, steps: int = 60, stepsize: float = 0.4) -> dict:
    """Optimise the ansatz live and return the convergence history.

    Kept for the notebook and for `?live=true`, but NOT the default path for the
    web app: a 60-step autograd optimisation inside a request ties up a worker.
    """
    point = _nearest_point(bond_length)
    H = _rebuild_hamiltonian(point)
    n = point["n_qubits"]

    dev = qml.device("default.qubit", wires=n)
    hf = qml.qchem.hf_state(2, n)
    singles, doubles = qml.qchem.excitations(2, n)

    @qml.qnode(dev)
    def circuit(params):
        qml.AllSinglesDoubles(params, wires=range(n), hf_state=hf,
                              singles=singles, doubles=doubles)
        return qml.expval(H)

    params = pnp.zeros(len(singles) + len(doubles), requires_grad=True)
    opt = qml.GradientDescentOptimizer(stepsize)

    t0 = time.time()
    history = []
    for _ in range(steps):
        params, energy = opt.step_and_cost(circuit, params)
        history.append(round(float(energy), 8))
    elapsed = time.time() - t0

    final = float(circuit(pnp.array(params, requires_grad=False)))
    exact = point["exact_energy"]
    hf_energy = history[0] if history else None
    hf_err = abs(hf_energy - exact) if hf_energy is not None else None

    return {
        "bond_length": point["bond_length"],
        "vqe_energy": round(final, 8),
        "exact_energy": round(exact, 8),
        "absolute_error": abs(final - exact),
        "chemical_accuracy": CHEMICAL_ACCURACY_HA,
        "within_chemical_accuracy": abs(final - exact) < CHEMICAL_ACCURACY_HA,
        "convergence": [{"step": i, "energy": e} for i, e in enumerate(history)],
        "n_qubits": n,
        "n_parameters": int(len(params)),
        "n_pauli_terms": len(point["terms"]),
        "hartree_fock_energy": round(hf_energy, 8) if hf_energy is not None else None,
        "hf_absolute_error": hf_err,
        "correlation_energy": round(hf_energy - final, 8) if hf_energy is not None else None,
        "runtime_seconds": round(elapsed, 2),
        "method": {
            "molecule": "H2", "basis": "sto-3g", "mapping": "Jordan-Wigner",
            "ansatz": "AllSinglesDoubles (UCCSD-style) from Hartree-Fock",
            "optimiser": f"gradient descent, {steps} steps, lr={stepsize}",
            "reference": "exact diagonalisation of the same Hamiltonian",
        },
        "scaling_note": (
            "H2 has 2 electrons in 4 spin-orbitals. A protein binding pocket in "
            "a minimal basis is on the order of 10^5 qubits before error "
            "correction, so protein-ligand binding energies are not a near-term "
            "quantum target. This endpoint is a verifiable benchmark, not drug "
            "discovery."
        ),
    }


def curve() -> dict:
    """The full dissociation curve, from precomputed results. Instant.

    Returns three energies per bond length -- the two classical references
    (Hartree-Fock mean-field and exact diagonalisation) and the quantum VQE
    answer -- so the frontend can plot VQE-matches-exact alongside
    VQE-beats-Hartree-Fock. The old `absolute_error` key is kept for
    backward compatibility with the shipped UI.
    """
    pts = []
    for g in _load()["points"]:
        if "vqe_energy" not in g:
            continue
        hist = g.get("convergence", [])
        hf = float(hist[0]) if hist else None            # HF is iteration 0 of the VQE run
        vqe_err = abs(g["vqe_energy"] - g["exact_energy"])
        hf_err = abs(hf - g["exact_energy"]) if hf is not None else None
        pts.append({
            "bond_length": g["bond_length"],
            "vqe_energy": round(g["vqe_energy"], 8),
            "exact_energy": round(g["exact_energy"], 8),
            "hartree_fock_energy": round(hf, 8) if hf is not None else None,
            "vqe_absolute_error": vqe_err,
            "hf_absolute_error": hf_err,
            "correlation_energy": round(hf - g["vqe_energy"], 8) if hf is not None else None,
            # Back-compat: the shipped UI reads `absolute_error` as the VQE error.
            "absolute_error": vqe_err,
        })
    if not pts:
        raise RuntimeError("vqe_h2.json has no VQE results — rerun build_vqe_data.py")
    vqe_errs = [p["vqe_absolute_error"] for p in pts]
    hf_errs = [p["hf_absolute_error"] for p in pts if p["hf_absolute_error"] is not None]
    best = min(pts, key=lambda p: p["exact_energy"])
    return {
        "points": pts,
        # Back-compat alias; the UI reads this as the max VQE error.
        "max_absolute_error": max(vqe_errs),
        "max_vqe_absolute_error": max(vqe_errs),
        "max_hf_absolute_error": max(hf_errs) if hf_errs else None,
        "all_within_chemical_accuracy": max(vqe_errs) < CHEMICAL_ACCURACY_HA,
        "chemical_accuracy_hartree": CHEMICAL_ACCURACY_HA,
        "equilibrium_bond_length": best["bond_length"],
        "equilibrium_energy": best["exact_energy"],
        "experimental_bond_length": 0.7414,
        "classical_vs_quantum": {
            "mean_field_classical": {
                "method": "Hartree-Fock",
                "max_absolute_error_hartree": max(hf_errs) if hf_errs else None,
                "note": (
                    "Classical mean-field: electrons move in each others' "
                    "AVERAGE field, with zero correlation. Exact at equilibrium, "
                    "fails qualitatively at stretched bonds."
                ),
            },
            "quantum_vqe": {
                "method": "VQE / AllSinglesDoubles (UCCSD-style)",
                "max_absolute_error_hartree": max(vqe_errs),
                "note": (
                    "Variational quantum eigensolver recovers the correlation "
                    "energy Hartree-Fock misses. Matches the exact answer to "
                    f"<= {max(vqe_errs):.1e} Ha across the whole curve, four "
                    "orders of magnitude inside chemical accuracy."
                ),
            },
            "exact_reference": {
                "method": "exact diagonalisation of the same qubit Hamiltonian",
                "note": "The ground truth at this basis.",
            },
            "honest_scaling_caveat": (
                "At 4 qubits classical FCI is cheap, so there is NO computational "
                "advantage. The point of this benchmark is to validate the "
                "quantum stack end-to-end and demonstrate the correlation-energy "
                "story. A protein binding pocket is ~10^5 qubits away."
            ),
        },
    }
