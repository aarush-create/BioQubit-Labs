# Deployment checklist

Everything in the repo is ready. These are the steps that must run on your
machine and in the hosting dashboards.

---

## 1. Retrain (~12 min)

The featuriser changed (ACE2 interface distance replaced relative position), so
the old `weights.npz` no longer matches it. The API refuses mismatched weights
rather than scoring nonsense, so this step is required.

```
cd C:\Users\aarus\Downloads\qvira\api
python train_vqc.py --data data\single_mut_effects.csv
```

No flags needed — the defaults (6 layers, 120 epochs, lr 0.05) reproduce the
shipped model.

**Expect:**
```
circuit: 4 qubits x 6 layers
features: ['blosum62', 'wt_volume', 'delta_volume', 'ace2_distance']
VQC                  acc~0.73  auc~0.75
svm_rbf              auc~0.75      <- we match this
mlp                  auc~0.77
logistic_regression  auc~0.78
```

Then check `api/metrics.json` says `"is_synthetic": false`.

## 2. Rebuild the surveillance cache (~1 min, needs internet)

Cached scores came from the previous model.

```
python sentinel.py
```

## 3. Check locally

Two terminals:

```
cd api && uvicorn main:app --reload
```
```
npm run dev
```

Confirm: tab 1 has data · **Results** button shows ~0.751 beside the baselines ·
scoring `N501Y` works · tab 5 responds.

---

## 4. GitHub

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

MUST NOT be included:
- `.venv/` (~378 MB of Windows binaries)
- `node_modules/`

## 5. Render (backend)

| Setting | Value |
|---|---|
| Root Directory | `api` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |

Environment:
```
GEMINI_API_KEY  = from https://aistudio.google.com/apikey
GEMINI_MODEL    = gemini-3.1-pro-preview
ALLOWED_ORIGINS = (fill in after step 6)
```

Deploy, then open the Render URL. It must show `"model_trained": true`.

## 6. Vercel (frontend)

Import the repo; Vite is auto-detected. Before deploying add:

```
VITE_API_URL = https://your-service.onrender.com
```

No trailing slash. Deploy, then paste your Vercel URL into Render's
`ALLOWED_ORIGINS` and let Render redeploy.

---

## Troubleshooting

**Red "Backend unavailable" banner on the live site**
`ALLOWED_ORIGINS` does not exactly match the Vercel URL. Compare character by
character, including `https://` and no trailing slash.

**Changed `VITE_API_URL` and nothing happened**
Vite bakes it in at build time. You must trigger a redeploy on Vercel.

**Render build fails on `pennylane` import**
Check `autoray==0.7.0` survived in `requirements.txt`. autoray >= 0.8 removed
`NumpyMimic`, which PennyLane 0.39 calls at import.

**First click on the live site is slow**
Render's free tier sleeps. Open the Render URL ~10 minutes before demoing; the
frontend also pings it on load.

**`/predict` returns 503**
`weights.npz` did not upload, or it was trained with a different featuriser.
Retrain and re-upload.

---

## On the day

- [ ] Warm Render ~10 min before
- [ ] Local `uvicorn` + `npm run dev` running as a fallback
- [ ] 3-minute video downloaded locally, not streamed
- [ ] `RESULTS.md` and the **Results** modal open in tabs — that is your evidence
- [ ] Read `docs/JURY_QA.md` as a team; each member owns one component
