"""
Q-VIRA API.

Design rules enforced here, in order of how much they matter to the jury:

1. Nothing is invented. If the model is untrained, /predict returns 503 with
   an explanation rather than a plausible-looking number.
2. Every numeric output is traceable. /predict returns the descriptors, the
   angles and the circuit parameters that produced the score.
3. Bad input gets a 4xx, not a 500.
4. The quantum score and the epidemiology are separate endpoints, because
   they are separate models with separate assumptions.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import features as feat
import mutation_features as mutfeat
from epidemiology import simulate
from quantum_engine import engine
import vqe as vqe_mod
import sentinel as sentinel_mod
from reference_panel import nearest_reference, panel_size, get_reference, list_references

API_VERSION = "2.1.0"

# The model was trained on SARS-CoV-2 RBD binding to the human ACE2 receptor.
# Any other reference is OUT OF DISTRIBUTION: the features are generic protein
# chemistry so a score will still be computed, but it is unvalidated. Different
# viruses use different receptors (influenza -> sialic acid, Ebola -> NPC1), and
# the relative_position feature learned which RBD positions contact ACE2, which
# means nothing in another protein. We surface this rather than hide it.
VALIDATED_REFERENCE_KEYWORDS = ("sars-cov-2", "sars cov 2", "sars-cov2")
VALIDATED_TARGET = "human ACE2 receptor binding"

# CRITICAL: the model was trained on the RECEPTOR-BINDING DOMAIN only, sites
# 331-531 in SARS-CoV-2 spike numbering (201 residues). The relative_position
# feature is the position WITHIN that window, not within the full 1273-residue
# spike. The reference sequences fetched from NCBI are full-length proteins, so
# we must map positions back into the trained window or every score is wrong:
# position 501 is 0.846 of the way through the RBD but only 0.393 of the way
# through the spike. Same input, completely different feature value.
TRAINED_DOMAIN = {"start": 331, "end": 531}   # inclusive, 1-indexed
TRAINED_DOMAIN_LENGTH = TRAINED_DOMAIN["end"] - TRAINED_DOMAIN["start"] + 1


def _distribution_check(reference_name: str | None) -> dict:
    """Is this reference inside the training distribution?"""
    name = (reference_name or "").lower()
    in_dist = any(k in name for k in VALIDATED_REFERENCE_KEYWORDS)
    if in_dist:
        return {
            "in_distribution": True,
            "validated_on": VALIDATED_TARGET,
            "note": "Reference matches the training distribution.",
        }
    return {
        "in_distribution": False,
        "validated_on": VALIDATED_TARGET,
        "note": (
            "OUT OF DISTRIBUTION. This model was trained only on SARS-CoV-2 RBD "
            "binding to human ACE2. The score below is computed from generic "
            "residue properties but is NOT validated for this protein, which "
            "uses a different receptor. Treat it as uncalibrated."
        ),
    }
HERE = os.path.dirname(os.path.abspath(__file__))

# Lock CORS down to the deployed frontend. Set this in Render's dashboard to
# your Vercel URL, comma-separated if you need previews.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not engine.is_trained:
        print("WARNING: weights.npz not found -- /predict will return 503.")
        print("         Run `python train_vqc.py --data <csv>` and redeploy.")
    else:
        print(f"Loaded trained VQC: {engine.metadata.get('data_source', 'unknown source')}")
    yield


app = FastAPI(title="Q-VIRA API", version=API_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # we use no cookies; '*' + credentials is invalid anyway
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------- schemas

class PredictRequest(BaseModel):
    """Score a VARIANT against a REFERENCE.

    The trained model scores substitutions, so it needs both. Supply either:
      - reference_name (from the panel) + mutations like ["N501Y"], or
      - reference + variant, two equal-length sequences.
    """
    reference_name: str | None = None
    mutations: list[str] | None = None
    reference: str | None = None
    variant: str | None = None


class SeirRequest(BaseModel):
    r0: float = Field(gt=0, le=20)
    population: int = Field(default=1_000_000, gt=100, le=2_000_000_000)
    incubation_days: float = Field(default=5.0, gt=0, le=60)
    infectious_days: float = Field(default=7.0, gt=0, le=60)
    initial_infected: int = Field(default=10, gt=0)
    days: int = Field(default=180, gt=10, le=1000)
    hospitalisation_rate: float = Field(default=0.04, ge=0, le=1)
    hospital_capacity: int = Field(default=2500, gt=0)


class VqeRequest(BaseModel):
    bond_length: float = Field(default=0.7414, gt=0.1, le=5.0)
    steps: int = Field(default=60, ge=10, le=200)
    live: bool = Field(default=False, description="re-run the optimisation now (slow)")


class CopilotRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    context: dict | None = None


# ---------------------------------------------------------------- routes

@app.get("/")
def health_check():
    """Honest status. Reports what is actually running, not what sounds good."""
    return {
        "status": "online",
        "api_version": API_VERSION,
        "quantum_backend": os.getenv("QVIRA_BACKEND", "default.qubit"),
        "quantum_framework": "PennyLane",
        "model_trained": engine.is_trained,
        "training_metadata": engine.metadata or None,
        "reference_panel_size": panel_size(),
        "featuriser": "physicochemical-v1",
        "copilot_enabled": bool(os.getenv("GEMINI_API_KEY")),
        "vqe_available": vqe_mod.available(),
        "sentinel_cached_at": sentinel_mod.load_cache().get("fetched_at"),
    }


@app.get("/metrics")
def metrics():
    """Held-out metrics from the last training run. Shown in the UI so the
    numbers on screen are auditable."""
    path = os.path.join(HERE, "metrics.json")
    if not os.path.exists(path):
        raise HTTPException(404, "No metrics.json -- model has not been trained.")
    with open(path) as fh:
        return json.load(fh)


@app.get("/references")
def references():
    """Reference sequences available for variant scoring.

    Each entry is flagged with whether the trained model is validated for it.
    """
    out = []
    for r in list_references():
        r = dict(r)
        r["in_distribution"] = _distribution_check(r["name"])["in_distribution"]
        out.append(r)
    return {"references": out, "validated_on": VALIDATED_TARGET}


def _parse_mutation(token: str, seq: str) -> tuple[int, str, str]:
    """Parse standard notation like 'N501Y' against a 1-indexed sequence."""
    token = token.strip().upper()
    if len(token) < 3:
        raise HTTPException(422, f"Cannot parse mutation '{token}' (expected e.g. N501Y)")
    wt, mut, pos_text = token[0], token[-1], token[1:-1]
    if not pos_text.isdigit():
        raise HTTPException(422, f"Cannot parse position in '{token}'")
    pos = int(pos_text)
    if not 1 <= pos <= len(seq):
        raise HTTPException(422, f"Position {pos} is outside the reference (1-{len(seq)})")
    actual = seq[pos - 1]
    if actual != wt:
        raise HTTPException(
            422,
            f"'{token}' says position {pos} is {wt}, but the reference has {actual}. "
            "Check the numbering offset of your reference sequence.",
        )
    return pos - 1, wt, mut


@app.post("/predict")
def predict(req: PredictRequest):
    if not engine.is_trained:
        raise HTTPException(
            503,
            "Model is untrained (no weights.npz). Q-VIRA does not emit scores "
            "from random parameters. Run train_vqc.py and redeploy.",
        )

    # --- resolve the reference sequence and the list of substitutions ---
    if req.reference_name and req.mutations:
        ref_seq = get_reference(req.reference_name)
        if ref_seq is None:
            raise HTTPException(
                404,
                f"No reference named '{req.reference_name}'. See GET /references.",
            )
        diffs = [_parse_mutation(t, ref_seq) for t in req.mutations]
    elif req.reference and req.variant:
        try:
            ref_seq = feat.parse_fasta(req.reference)
            var_seq = feat.parse_fasta(req.variant)
            diffs = mutfeat.diff_sequences(ref_seq, var_seq)
        except (feat.SequenceError, mutfeat.MutationError) as exc:
            raise HTTPException(422, str(exc))
    else:
        raise HTTPException(
            422,
            "Provide either (reference_name + mutations) or (reference + variant).",
        )

    if len(diffs) > 50:
        raise HTTPException(422, f"{len(diffs)} substitutions is more than this model scores (max 50).")

    dist = _distribution_check(req.reference_name)

    # --- score every substitution independently ---
    n = len(ref_seq)
    in_domain_flags = []
    scored = []
    for idx, wt, mut in diffs:
        position = idx + 1                      # 1-indexed, as users write it
        if dist["in_distribution"]:
            # Map into the trained RBD window (sites 331-531).
            offset = position - TRAINED_DOMAIN["start"]
            within = 0 <= offset < TRAINED_DOMAIN_LENGTH
            rel_pos = offset / TRAINED_DOMAIN_LENGTH if within else min(max(offset / TRAINED_DOMAIN_LENGTH, 0.0), 1.0)
            in_domain_flags.append(within)
        else:
            # Out-of-distribution reference: no trained window exists, so fall
            # back to whole-protein position. Already flagged as unvalidated.
            rel_pos = idx / n
            in_domain_flags.append(False)
        try:
            angles, explain = mutfeat.featurise_mutation(wt, mut, rel_pos, site=position)
        except mutfeat.MutationError as exc:
            raise HTTPException(422, str(exc))
        r = engine.score(angles)
        scored.append({
            "mutation": f"{wt}{position}{mut}",
            "position": position,
            "in_trained_domain": in_domain_flags[-1],
            "score": round(r["threat_score"], 4),
            "stderr": round(r.get("threat_score_stderr", 0.0), 4),
            "descriptors": explain["descriptors"],
            "has_structure": mutfeat.has_ace2_structure(position),
            "state_distribution": engine.distribution(angles),
        })

    # Aggregate: the variant's score is driven by its most impactful single
    # substitution. The model was trained on SINGLE mutants, so it has no
    # information about epistasis -- we state that rather than pretend the
    # combination is modelled.
    worst = max(scored, key=lambda s: s["score"])

    outside = [s["mutation"] for s in scored if not s["in_trained_domain"]]
    if dist["in_distribution"] and outside:
        dist = dict(dist)
        dist["in_distribution"] = False
        dist["note"] = (
            f"Position(s) {', '.join(outside)} fall outside the receptor-binding "
            f"domain (spike sites {TRAINED_DOMAIN['start']}-{TRAINED_DOMAIN['end']}), "
            "which is the only region this model was trained on. Scores for those "
            "substitutions are extrapolated and NOT validated."
        )

    return {
        "distribution": dist,
        "trained_domain": {
            "name": "SARS-CoV-2 spike receptor-binding domain",
            "spike_sites": f"{TRAINED_DOMAIN['start']}-{TRAINED_DOMAIN['end']}",
            "length": TRAINED_DOMAIN_LENGTH,
        },
        "threat_score": worst["score"],
        "threat_score_stderr": worst["stderr"],
        "driver_mutation": worst["mutation"],
        "mutations": scored,
        "n_substitutions": len(scored),
        "reference_length": n,
        "features": {"descriptors": worst["descriptors"], "method": "mutation-delta-v1"},
        "state_distribution": worst["state_distribution"],
        "quantum": {
            "n_qubits": engine.weights.shape[1],
            "n_layers": int(engine.weights.shape[0]),
            "n_parameters": int(engine.weights.size + 2),
            "ansatz": "data-reuploading-StronglyEntanglingLayers",
            "backend": os.getenv("QVIRA_BACKEND", "default.qubit"),
            "shots": int(os.getenv("QVIRA_SHOTS", "2048")),
        },
        "model_card": {
            "predicts": engine.metadata.get("label", "see metrics.json"),
            "trained_on": engine.metadata.get("data_source", "unknown"),
            "held_out_auc": engine.metadata.get("vqc", {}).get("roc_auc"),
            "caveat": (
                "Per-substitution score from 4 residue-property descriptors, "
                "trained on SARS-CoV-2 RBD/ACE2 single mutants only. Epistasis "
                "between combined mutations is NOT modelled, and other viruses "
                "are out of distribution. Not an outbreak forecast, not a "
                "clinical tool."
            ),
        },
    }


@app.post("/seir")
def seir(req: SeirRequest):
    try:
        return simulate(
            r0=req.r0,
            population=req.population,
            incubation_days=req.incubation_days,
            infectious_days=req.infectious_days,
            initial_infected=req.initial_infected,
            days=req.days,
            hospitalisation_rate=req.hospitalisation_rate,
            hospital_capacity=req.hospital_capacity,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/sentinel")
def sentinel_feed():
    """Cached surveillance feed: recently deposited SARS-CoV-2 spikes, with
    their RBD substitutions scored by the trained VQC.

    Cached deliberately — see sentinel.py. The fetch timestamp is returned so
    the UI can show that this is not live data.
    """
    cache = sentinel_mod.load_cache()
    if not cache:
        raise HTTPException(
            503,
            "No sentinel cache. Run `python sentinel.py` to build it, then commit "
            "sentinel_cache.json.",
        )
    return cache


@app.post("/sentinel/refresh")
def sentinel_refresh():
    """Re-query NCBI and rebuild the cache.

    Disabled in production by default: Render's filesystem is ephemeral, so a
    refresh there is lost on restart. Build the cache locally and commit it.
    Set ALLOW_SENTINEL_REFRESH=1 to enable.
    """
    if os.getenv("ALLOW_SENTINEL_REFRESH") != "1":
        raise HTTPException(
            403,
            "Refresh is disabled. The cache is built locally with "
            "`python sentinel.py` and committed, because this host's filesystem "
            "is ephemeral. Set ALLOW_SENTINEL_REFRESH=1 to override.",
        )
    try:
        return sentinel_mod.refresh()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@app.get("/vqe/geometries")
def vqe_geometries():
    """Bond lengths available, with exact reference energies."""
    if not vqe_mod.available():
        raise HTTPException(503, "vqe_h2.json missing. Run build_vqe_data.py and redeploy.")
    return {"geometries": vqe_mod.geometries(), "molecule": "H2", "basis": "sto-3g"}


@app.post("/vqe")
def run_vqe(req: VqeRequest):
    """Run a REAL VQE at one geometry and compare against exact diagonalisation."""
    if not vqe_mod.available():
        raise HTTPException(503, "vqe_h2.json missing. Run build_vqe_data.py and redeploy.")
    # Serve the precomputed result by default. Optimising in-request blocked
    # the event loop and made the tab unusable; `live=true` re-runs it for
    # anyone who wants to watch it happen (and will be slow).
    if not req.live:
        result = vqe_mod.stored(req.bond_length)
        if result is not None:
            return result
    try:
        return vqe_mod.run(req.bond_length, steps=req.steps)
    except Exception as exc:
        raise HTTPException(500, f"VQE failed: {type(exc).__name__}: {exc}")


@app.get("/vqe/curve")
def vqe_curve():
    """VQE across every stored geometry — the H2 dissociation curve."""
    if not vqe_mod.available():
        raise HTTPException(503, "vqe_h2.json missing. Run build_vqe_data.py and redeploy.")
    return vqe_mod.curve()


@app.post("/copilot")
def copilot(req: CopilotRequest):
    """Gemini-backed explainer.

    Gemini explains; it never computes. The numbers come from the quantum and
    SEIR endpoints and are passed in as context. The system prompt forbids
    inventing figures, which is what keeps the demo defensible.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(503, "Copilot disabled: GEMINI_API_KEY is not set.")

    import httpx

    # Default to a FREE-TIER model. gemini-3.1-pro-preview is paid-tier only
    # (Google AI Studio shows "Not available" on Free), and the copilot only
    # explains numbers the other endpoints already computed -- it does no
    # reasoning that needs a Pro model. Override with GEMINI_MODEL if you have
    # billing enabled.
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    system = (
        "You are the Q-VIRA copilot, explaining a hybrid quantum-classical "
        "bioinformatics dashboard to a technical judge.\n"
        "RULES:\n"
        "1. Use ONLY the numbers in CONTEXT. Never invent or estimate a figure.\n"
        "2. If the answer is not in CONTEXT, say you do not have it.\n"
        "3. Be precise about what is real: a 4-qubit PennyLane simulation with "
        "a data re-uploading ansatz, physicochemical descriptors (not ESM-2 "
        "unless CONTEXT says so), and a deterministic SEIR scenario.\n"
        "4. Never claim quantum advantage. At 4 qubits there is none; the "
        "circuit is a feasibility study.\n"
        "5. This is a research prototype, not a clinical or public-health tool.\n"
        "6. Answer in under 120 words."
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": f"CONTEXT:\n{json.dumps(req.context or {}, indent=2)}\n\n"
                                f"QUESTION: {req.question}"
                    }
                ],
            }
        ],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400},
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers={"x-goog-api-key": api_key}, json=payload)
        if resp.status_code != 200:
            raise HTTPException(502, f"Gemini error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Copilot upstream failure: {type(exc).__name__}")

    if not text:
        raise HTTPException(502, "Copilot returned an empty response.")
    return {"answer": text, "model": model, "grounded_in": list((req.context or {}).keys())}
