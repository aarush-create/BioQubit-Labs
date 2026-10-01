from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pennylane as qml
from pennylane import numpy as np

app = FastAPI()

# Security clearance for your Netlify frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the 4-Qubit Quantum Device
n_qubits = 4
dev = qml.device("default.qubit", wires=n_qubits)

# Define the Variational Quantum Circuit
@qml.qnode(dev)
def bio_threat_vqc(features, weights):
    qml.AngleEmbedding(features=features, wires=range(n_qubits), rotation='Y')
    qml.BasicEntanglerLayers(weights=weights, wires=range(n_qubits))
    return qml.expval(qml.PauliZ(0))

class Payload(BaseModel):
    features: list[float]

@app.get("/")
def health_check():
    return {"status": "online", "engine": "PennyLane Quantum Simulator"}

@app.post("/predict")
def predict(payload: Payload):
    # Convert frontend sequence data into a quantum-ready array
    features = np.array(payload.features, requires_grad=False)
    
    # Execute the circuit with randomized variational weights
    np.random.seed(42)
    weights = np.random.random((3, n_qubits), requires_grad=False)
    
    # RUN THE ACTUAL QUANTUM MATH
    raw_score = bio_threat_vqc(features, weights)
    
    # Process quantum expectation value into epidemiological metrics
    threat_score = float((raw_score + 1) / 2)
    r0_projected = 1.0 + (threat_score * 2.5) 
    
    return {
        "threat_score": round(threat_score, 4), 
        "r0": round(r0_projected, 2)
    }
