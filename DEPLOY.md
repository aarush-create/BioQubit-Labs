# Deployment checklist

Everything in the repo is ready. These are the steps that must run on your
machine and in the hosting dashboards.

---

## 1. Retrain (~12 min, only if the featuriser or stack changed)

The committed `api/weights.npz` is the shipped 2-qubit model. Retraining is
only needed if you change the featuriser or want to reproduce the number from
scratch; the API refuses mismatched weights rather than scoring nonsense.

```
cd C:\Users\aarus\Downloads\qvira\api
python train_vqc.py --data data\single_mut_effects.csv ^
--features 4,6,2,8 --readout probs --encoding dense --axes Y,Z ^
--seeds 3 --epochs 120 --val-frac 0.0
```

This reproduces the shipped 2-qubit SARS-CoV-2 model (dense encoding, four
features). The cross-virus model (`weights_panel.npz`) is committed; its
training command is in the README under "Reproducing the cross-virus model".

**Expect:**
```
circuit: 2 qubits x 6 layers (4 features on 2 wires)
features: ['blosum62', 'wt_volume', 'delta_volume', 'ace2_distance']
test AUC = 0.742 +/- 0.002 (3-seed spread)
svm_rbf auc~0.76
mlp auc~0.77
logistic_regression auc~0.78
```

Then check `api/metrics.json` says `"is_synthetic": false`.

## 2. Rebuild the surveillance cache (~1 min, needs internet)

Cached scores came from the previous model.

```
python sentinel.py
```

## 3. Validate the Qiskit backend (~1-3 min, one-off per stack change)

Only re-run if you've changed `pennylane-qiskit` or the circuit code. The
Aer simulator is validated against the analytic `default.qubit` backend:

```
python parity_check.py          # exact-equality for the analytic path
python convergence_check.py     # 1/sqrt(N) convergence for the sampled path
```

Expect `convergence_check` to report a fitted scaling exponent near -0.5 and
no fixture above 2 sigma — that's the proof the backends compute the same
state. Keep both scripts committed as the audit trail.

## 4. Check locally

Two terminals:

```
cd api && uvicorn main:app --reload
```
```
npm run dev
```

Confirm: tab 1 has data · **Results** button shows the baselines · scoring
`N501Y` works · the **Quantum chemistry** tab shows three lines (Classical
Hartree–Fock, Quantum VQE, Exact) · `GET /` reports
`"quantum_backend": "qiskit.aer"`.

---

## 5. GitHub

**Delete the dead files** (click → trash icon → Commit changes):
- `api/autonomous_sentinel.py`
- `api/pathogen_db.json`

**Upload** everything inside `qvira` (Add file → Upload files).

MUST be included (the deployed app breaks without them):
- `api/weights.npz`
- `api/metrics.json`
- `api/reference_panel.json`
- `api/sentinel_cache.json`
- `api/vqe_h2.json`
- `api/ace2_distance.json`
- `api/weights_panel.npz`
- `api/metrics_panel.json`
- `api/panel_catalog.json`
- `api/burial.json`
- `.vercelignore`  **(leading dot — Windows File Explorer strips it; create
  this from the GitHub web UI or `git mv vercelignore .vercelignore`)**

MUST NOT be included:
- `.venv/` (hundreds of MB of binaries, platform-specific)
- `node_modules/`
- `api/` under Vercel's bundle (handled by `.vercelignore`)

## 6. Render (backend)

| Setting | Value |
|---|---|
| Root Directory | `api` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |

Environment (dashboard values override `render.yaml`):
```
GEMINI_API_KEY = from https://aistudio.google.com/apikey
GEMINI_MODEL = gemini-2.5-flash               # free tier; Pro models need billing
XAI_API_KEY = from https://console.x.ai       # fallback when Gemini is down
PYTHON_VERSION = 3.12.8                       # 3.13 is also fine on this stack
ALLOWED_ORIGINS = (fill in after step 7)
QVIRA_BACKEND = qiskit.aer                    # pulled from render.yaml; set to
                                              # default.qubit here if OOM-killed
QVIRA_SHOTS = 2048
```

### Memory and the Aer simulator

Render's free tier gives 512 MB RAM. The Qiskit install is heavy and Aer is
heavier. If the deploy OOM-kills on startup, set `QVIRA_BACKEND=default.qubit`
in the dashboard (overrides `render.yaml`) and redeploy — the Qiskit deps stay
installed but Aer is never imported, so RSS drops. Scores are identical within
shot noise (that's what `convergence_check.py` proved), so the fallback is a
resource trade-off, not a correctness one.

### Copilot fallback

The copilot tries Gemini first and falls through to Grok on any failure — a
quota reset, a 429, a timeout, a renamed model. Either key alone is enough;
with both, a demo survives one provider going down mid-question. The reply
says which provider answered, so a fall-through is visible rather than hidden.

Verify both keys actually reached the process — a key with a trailing space, or
one added without restarting the service, leaves the chain one provider long and
nothing says so until the fallback is needed:

```bash
curl -s https://q-vira-api.onrender.com/ | python3 -m json.tool | grep copilot
# "copilot_providers": ["gemini", "grok"], <- both, not one
# "copilot_enabled": true,
```

Optional:
```
XAI_MODEL = grok-4.7         # on a model error the chain asks /v1/models what
                             # this key can use and retries once
COPILOT_ORDER = gemini,grok  # reorder, or name one provider to pin it
```

### Surveillance feed

The feed seeds from the committed `sentinel_cache.json` and refreshes itself on
a background thread once the cache passes `SENTINEL_MAX_AGE_HOURS` (12 by
default). A page load is always served from memory, so nothing ever waits on
NCBI. This host's disk is ephemeral, so the fresh payload lives in memory and a
restart falls back to the committed cache and refreshes again.

```
SENTINEL_AUTO_REFRESH = 1          # 0 pins the feed to the committed cache
SENTINEL_MAX_AGE_HOURS = 12
SENTINEL_MIN_RETRY_SECONDS = 900   # floor between NCBI queries
```

Deploy, then open the Render URL. It must show `"model_trained": true` and
`"quantum_backend": "qiskit.aer"` (or `default.qubit` if you fell back).

## 7. Vercel (frontend)

Import the repo; Vite is auto-detected. Before deploying add:

```
VITE_API_URL = https://your-service.onrender.com
```

No trailing slash. Deploy, then paste your Vercel URL into Render's
`ALLOWED_ORIGINS` and let Render redeploy.

**The `.vercelignore` file (leading dot!) must be in the repo root** — without
it Vercel bundles the entire `api/` directory as a serverless function and
fails with `LAMBDA_SIZE_EXCEEDED` (658 MB > 500 MB limit) because of the
PennyLane + Qiskit install.

---

## Troubleshooting

**Red "Backend unavailable" banner on the live site**
`ALLOWED_ORIGINS` does not exactly match the Vercel URL. Compare character by
character, including `https://` and no trailing slash.

**Vercel: `LAMBDA_SIZE_EXCEEDED` (bundle > 500 MB)**
`.vercelignore` is missing or named without the leading dot. Check the file
listing on GitHub — Windows File Explorer sometimes strips the dot. Fix by
renaming `vercelignore` → `.vercelignore` on the GitHub web UI (edit → change
filename at the top).

**Changed `VITE_API_URL` and nothing happened**
Vite bakes it in at build time. You must trigger a redeploy on Vercel.

**Render build fails on `pennylane-qiskit` resolve**
The pin set in `api/requirements.txt` is verified for Linux. If pip errors on
a transitive like `sspilib` (Windows-only, pulled by `qiskit-ibm-runtime`),
your `requirements.txt` was `pip freeze`'d on Windows — regenerate from the
committed pins, don't `pip freeze` across platforms.

**Render OOM-killed on startup**
The Qiskit stack exceeds free-tier memory. Set `QVIRA_BACKEND=default.qubit`
in the Render dashboard (overrides `render.yaml`) and redeploy.

**First click on the live site is slow**
Render's free tier sleeps. Open the Render URL ~10 minutes before demoing; the
frontend also pings it on load.

**`/predict` returns 503**
`weights.npz` did not upload, or it was trained with a different featuriser.
Retrain and re-upload.

**`/vqe/curve` returns points without `hartree_fock_energy`**
The deployed `vqe.py` is older than this round. Pull latest; the new curve()
reads HF from `convergence[0]` of the committed `vqe_h2.json` with no retrain
needed.

---

## On the day

- [ ] Warm Render ~10 min before (`curl https://q-vira-api.onrender.com/`)
- [ ] Local `uvicorn` + `npm run dev` running as a fallback
- [ ] 3-minute video downloaded locally, not streamed
- [ ] `RESULTS.md` and the **Results** modal open in tabs — that is your evidence
- [ ] Read `docs/JURY_QA.md` as a team; each member owns one component
- [ ] `GET /` on the deployed API shows `quantum_backend: qiskit.aer` and
      `vqe_available: true`
- [ ] Quantum chemistry tab renders three lines (Classical HF, Quantum VQE, Exact)
      with the HF-vs-exact gap caption visible
