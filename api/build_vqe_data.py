"""
Precompute H2 Hamiltonians for the live VQE endpoint.

Run locally once (needs pyscf), then commit vqe_h2.json:
    pip install pyscf
    python build_vqe_data.py

Why precompute: the Hartree-Fock step needs PySCF, which is a heavy dependency
and will not fit comfortably on a free-tier dyno. The qubit Hamiltonian itself
is just a list of Pauli strings and coefficients, so we compute those offline
and ship them. The VQE optimisation at serve time runs on PennyLane alone.
"""
import json, os
import numpy as np
import pennylane as qml

BONDS = [0.3, 0.4, 0.5, 0.6, 0.7414, 0.9, 1.1, 1.3, 1.6, 2.0, 2.4]
out = {"molecule": "H2", "basis": "sto-3g", "mapping": "jordan_wigner", "points": []}

for R in BONDS:
    coords = np.array([[0.0, 0.0, -R / 2], [0.0, 0.0, R / 2]])
    H, n = qml.qchem.molecular_hamiltonian(["H", "H"], coords, basis="sto-3g", unit="angstrom")
    coeffs, ops = H.terms()
    terms = []
    for c, op in zip(coeffs, ops):
        # Serialise each Pauli term as {wire: 'X'|'Y'|'Z'}; identity = {}
        pauli = {}
        for o in (op.operands if hasattr(op, "operands") else [op]):
            name = o.name if isinstance(o.name, str) else o.name[0]
            if name in ("PauliX", "PauliY", "PauliZ"):
                pauli[int(o.wires[0])] = name[-1]
        terms.append({"coeff": float(c), "pauli": pauli})
    exact = float(np.linalg.eigvalsh(qml.matrix(H))[0])

    # Also RUN the VQE here and store the result + convergence history, so the
    # web app can serve a verified benchmark instantly instead of optimising
    # inside a request. Optimising in-request blocked the server and made the
    # tab unusable; this is the same computation, done once, ahead of time.
    dev = qml.device("default.qubit", wires=n)
    hf = qml.qchem.hf_state(2, n)
    singles, doubles = qml.qchem.excitations(2, n)

    @qml.qnode(dev)
    def circuit(params):
        qml.AllSinglesDoubles(params, wires=range(n), hf_state=hf,
                              singles=singles, doubles=doubles)
        return qml.expval(H)

    from pennylane import numpy as pnp
    params = pnp.zeros(len(singles) + len(doubles), requires_grad=True)
    opt = qml.GradientDescentOptimizer(0.4)
    history = []
    for _ in range(60):
        params, energy = opt.step_and_cost(circuit, params)
        history.append(round(float(energy), 8))
    vqe_energy = float(circuit(pnp.array(params, requires_grad=False)))

    out["points"].append({
        "bond_length": R, "n_qubits": int(n), "terms": terms,
        "exact_energy": exact,
        "vqe_energy": vqe_energy,
        "absolute_error": abs(vqe_energy - exact),
        "convergence": history,
        "n_parameters": int(len(params)),
    })
    print(f"R={R:5.3f}  {len(terms):3d} terms  exact={exact:.8f}  "
          f"vqe={vqe_energy:.8f}  err={abs(vqe_energy-exact):.1e}")

path = os.path.join(os.path.dirname(__file__), "vqe_h2.json")
json.dump(out, open(path, "w"))
print(f"\nWrote {len(out['points'])} geometries to {path}")
