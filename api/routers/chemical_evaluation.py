from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

# IBM Qiskit Imports
from qiskit.quantum_info import SparsePauliOp
from qiskit.circuit.library import EfficientSU2
from qiskit_algorithms.optimizers import COBYLA
from qiskit_algorithms import VQE
from qiskit.primitives import Estimator

router = APIRouter()

class VQEConvergence(BaseModel):
    iteration: int
    energy_hartree: float

class EvaluationMetrics(BaseModel):
    model_target: str
    classical_r2: float
    quantum_r2: float
    rmse_improvement_pct: float
    vqe_data: List[VQEConvergence]

@router.get("/api/v1/evaluation", response_model=EvaluationMetrics)
async def fetch_chemical_evaluation():
    # 1. Define the Observable (Hamiltonian)
    # This specific Pauli string represents the H2 molecule ground state.
    # For BioQubit Labs, you will eventually replace this with the Hamiltonian 
    # representing your RNA structure or protein folding targets.
    h2_op = SparsePauliOp.from_list([
        ("II", -1.0523732),
        ("IZ",  0.3979374),
        ("ZI", -0.3979374),
        ("ZZ", -0.0112801),
        ("XX",  0.1809312)
    ])
    
    # 2. Setup the Quantum Circuit (Ansatz) and Classical Optimizer
    ansatz = EfficientSU2(num_qubits=2, reps=1, entanglement="linear")
    optimizer = COBYLA(maxiter=50)
    estimator = Estimator() # Local quantum simulator

    # 3. The Callback: This is the bridge between Qiskit and your React UI
    history = []
    
    def store_intermediate_result(eval_count, parameters, mean, std):
        # Qiskit fires this function every time the optimizer tests a new circuit parameter
        history.append({
            "iteration": eval_count,
            "energy_hartree": mean
        })

    # 4. Initialize and run the VQE
    vqe = VQE(estimator, ansatz, optimizer, callback=store_intermediate_result)
    result = vqe.compute_minimum_eigenvalue(h2_op)

    return EvaluationMetrics(
        model_target="H2 Molecule Ground State (Live Qiskit Run)",
        classical_r2=0.76, # Replace with actual classical baseline from your script
        quantum_r2=0.88,   # Replace with actual quantum model accuracy
        rmse_improvement_pct=15.4,
        vqe_data=history   # Pushing the REAL array of quantum iterations to the UI
    )
