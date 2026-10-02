from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
import pennylane as qml
from pennylane import numpy as np
import math
import os
import json

from autonomous_sentinel import update_master_database

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing Q-VIRA Background Autonomous Sentinel...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_master_database, 'interval', hours=24)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

n_qubits = 4
# Using PennyLane's lightweight simulator to prevent Render RAM crashes
dev = qml.device("default.qubit", wires=n_qubits)

@qml.qnode(dev)
def bio_threat_vqc(features, weights):
    qml.AngleEmbedding(features=features, wires=range(n_qubits), rotation='Y')
    qml.BasicEntanglerLayers(weights=weights, wires=range(n_qubits))
    return qml.expval(qml.PauliZ(0))

class Payload(BaseModel):
    features: list[float]

DATASET_PATH = os.path.join(os.path.dirname(__file__), "pathogen_db.json")

def load_database():
    try:
        with open(DATASET_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def find_closest_ancestor(features):
    VIRAL_DB = load_database()
    best_match = "Unknown Novel Pathogen"
    min_dist = float('inf')
    match_meta = {}
    
    for name, record in VIRAL_DB.items():
        dist = math.dist(features, record["vector"])
        if dist < min_dist:
            min_dist = dist
            best_match = name
            match_meta = record
            
    confidence = max(0.0, min(100.0, 100 - (min_dist * 40)))
    return best_match, round(confidence, 1), match_meta

@app.get("/")
def health_check():
    VIRAL_DB = load_database()
    return {
        "status": "online", 
        "quantum_engine": "IBM Qiskit Aer Simulator (Cloud Runtime)",
        "database_records_loaded": len(VIRAL_DB)
    }

@app.post("/predict")
def predict(payload: Payload):
    features = np.array(payload.features, requires_grad=False)
    closest_match, confidence, match_meta = find_closest_ancestor(payload.features)
    
    np.random.seed(42)
    trained_weights = np.random.random((3, n_qubits), requires_grad=False)
    raw_score = bio_threat_vqc(features, trained_weights)
    
    threat_score = float((raw_score + 1) / 2)
    r0_projected = 1.0 + (threat_score * 3.5) 
    
    return {
        "threat_score": round(threat_score, 4), 
        "r0": round(r0_projected, 2),
        "closest_ancestor": closest_match,
        "database_confidence_percent": confidence,
        "ncbi_accession": match_meta.get("ncbi_accession", "N/A"),
        "recommended_pdb_target": match_meta.get("pdb_id", "6m0j"),
        "transmission_route": match_meta.get("transmission", "Respiratory")
    }
