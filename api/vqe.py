"""
Live VQE for H2.

This replaces the old "Drug Discovery" panel, which displayed a number computed
in JavaScript as -(4.2 + threat_score) and labelled it a 12-qubit Qiskit VQE of
a protein pocket with a Paxlovid derivative. No VQE was run.

What runs here instead is a real variational quantum eigensolver:
  - the qubit Hamiltonian comes from a genuine Hartree-Fock calculation
    (precomputed with PySCF by build_vqe_data.py, shipped as vqe_h2.json)
  - the ansatz is optimised at request time on PennyLane
  - the result is compared against exact diagonalisation of the same
    Hamiltonian, so the answer is falsifiable

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
    return {
        "bond_length": p["bond_length"],
        "vqe_energy": round(p["vqe_energy"], 8),
        "exact_energy": round(p["exact_energy"], 8),
        "absolute_error": err,
        "chemical_accuracy": 1.6e-3,
        "within_chemical_accuracy": err < 1.6e-3,
        "convergence": [{"step": i, "energy": e} for i, e in enumerate(hist)],
        "n_qubits": p["n_qubits"],
        "n_parameters": p.get("n_parameters"),
        "n_pauli_terms": len(p["terms"]),
        "hartree_fock_energy": hist[0] if hist else None,
        "correlation_energy": round(hist[0] - p["vqe_energy"], 8) if hist else None,
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

    return {
        "bond_length": point["bond_length"],
        "vqe_energy": round(final, 8),
        "exact_energy": round(exact, 8),
        "absolute_error": abs(final - exact),
        "chemical_accuracy": 1.6e-3,
        "within_chemical_accuracy": abs(final - exact) < 1.6e-3,
        "convergence": [{"step": i, "energy": e} for i, e in enumerate(history)],
        "n_qubits": n,
        "n_parameters": int(len(params)),
        "n_pauli_terms": len(point["terms"]),
        "hartree_fock_energy": history[0] if history else None,
        "correlation_energy": round(history[0] - final, 8) if history else None,
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
    """The full dissociation curve, from precomputed results. Instant."""
    pts = []
    for g in _load()["points"]:
        if "vqe_energy" not in g:
            continue
        pts.append({
            "bond_length": g["bond_length"],
            "vqe_energy": round(g["vqe_energy"], 8),
            "exact_energy": round(g["exact_energy"], 8),
            "absolute_error": abs(g["vqe_energy"] - g["exact_energy"]),
        })
    if not pts:
        raise RuntimeError("vqe_h2.json has no VQE results — rerun build_vqe_data.py")
    errs = [p["absolute_error"] for p in pts]
    best = min(pts, key=lambda p: p["exact_energy"])
    return {
        "points": pts,
        "max_absolute_error": max(errs),
        "all_within_chemical_accuracy": max(errs) < 1.6e-3,
        "equilibrium_bond_length": best["bond_length"],
        "equilibrium_energy": best["exact_energy"],
        "experimental_bond_length": 0.7414,
    }
