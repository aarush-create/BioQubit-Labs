from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pennylane as qml
from pennylane import numpy as np

app = FastAPI()

# Allow your Netlify frontend to talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4-Qubit Simulator
n_qubits = 4
dev = qml.device("default.qubit", wires=n_qubits)

@qml.qnode(dev)
def bio_threat_vqc(features, weights):
    qml.AngleEmbedding(features=features, wires=range(n_qubits), rotation='Y')
    qml.BasicEntanglerLayers(weights=weights, wires=range(n_qubits))
    return qml.expval(qml.PauliZ(0))

class Payload(BaseModel):
    features: list[float]

@app.post("/predict")
def predict(payload: Payload):
    # Convert incoming frontend data to PennyLane array
    features = np.array(payload.features, requires_grad=False)
    
    # Run the quantum circuit
    np.random.seed(42)
    weights = np.random.random((3, n_qubits), requires_grad=False)
    raw_score = bio_threat_vqc(features, weights)
    
    # Calculate live outputs
    threat_score = float((raw_score + 1) / 2)
    r0_projected = 1.0 + (threat_score * 2.5) 
    
    return {
        "threat_score": round(threat_score, 4), 
        "r0": round(r0_projected, 2)
    }
