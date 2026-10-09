"""Is the VQC-to-classical gap bigger than the noise on the test set?

The deck says the VQC places fourth of five, 0.7468 against 0.7799 for logistic
regression. That ordering is read off ONE held-out set of 946 rows. This asks
the question that ordering invites: given only 946 rows, how precisely is any of
these AUCs known, and is the 0.033 gap larger than that precision?

Method: the shipped weights and the shipped split, so this describes the model
that is actually deployed. Then a PAIRED bootstrap -- the same resampled rows
scored by both models on every draw, which is the correct test for a difference
measured on one shared test set. An unpaired comparison would overstate the
uncertainty by ignoring that both models see identical rows.
"""
import json, sys
import numpy as np
from sklearn.metrics import roc_auc_score

import os
API = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, API)
import train_vqc as T
from mutation_features import SELECTED, NAMES
import pennylane as qml
from pennylane import numpy as pnp

DATA = os.path.join(API, 'data', 'single_mut_effects.csv')
SEED = 0           # train_vqc.py --seed default: reproduces the shipped split

USAGE = """
    python bootstrap_gap.py            # 10,000 resamples, about 30 seconds

Reads the committed weights.npz, so it describes the deployed model rather than
a fresh training run. Writes nothing except bootstrap_gap.json.
"""

X_raw, y, sites, source = T.load_dms(DATA)
cols = list(SELECTED)
X = T._scale_block(X_raw[:, cols], cols)

# the shipped split, reproduced exactly from train_vqc.py
rng = np.random.default_rng(SEED)
uniq = np.unique(sites); rng.shuffle(uniq)
n_test = max(1, int(0.25 * len(uniq)))
te = np.array([s in set(uniq[:n_test].tolist()) for s in sites]); tr = ~te
Xtr, ytr, Xte, yte = X[tr], y[tr], X[te], y[te]
print(f'train {tr.sum()} rows / {len(uniq)-n_test} sites | '
      f'test {te.sum()} rows / {n_test} sites')

# the shipped VQC, loaded not retrained
d = np.load(f'{API}/weights.npz', allow_pickle=True)
w, r = d['weights'], d['readout']
n_q = Xtr.shape[1]
dev = qml.device('default.qubit', wires=n_q)

@qml.qnode(dev)
def circuit(features, weights):
    for layer in range(weights.shape[0]):
        qml.AngleEmbedding(features=features, wires=range(n_q), rotation='Y')
        qml.StronglyEntanglingLayers(weights[layer:layer+1], wires=range(n_q))
    return qml.expval(qml.PauliZ(0))

z = np.asarray(circuit(np.asarray(Xte, float), pnp.array(w, requires_grad=False)), dtype=float)
p_vqc = 1.0 / (1.0 + np.exp(-(r[0] * z + r[1])))

# the classical baselines, same features, same split
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.neural_network import MLPClassifier
models = {
    'logistic regression': LogisticRegression(max_iter=2000),
    'neural network (MLP)': MLPClassifier(hidden_layer_sizes=(16,), max_iter=2000, random_state=0),
    'support vector machine': SVC(probability=True, random_state=0),
}
preds = {'VQC (ours)': p_vqc}
for name, mdl in models.items():
    mdl.fit(Xtr, ytr)
    preds[name] = mdl.predict_proba(Xte)[:, 1]

print('\npoint estimates (this is the deck table):')
for n, p in sorted(preds.items(), key=lambda kv: -roc_auc_score(yte, kv[1])):
    print(f'  {n:24} {roc_auc_score(yte, p):.4f}')

# paired bootstrap over the held-out rows
B = 10000
rs = np.random.default_rng(12345)
idx = np.arange(len(yte))
boot = {n: [] for n in preds}
diff = {n: [] for n in preds if n != 'VQC (ours)'}
for _ in range(B):
    s = rs.choice(idx, len(idx), replace=True)
    if len(np.unique(yte[s])) < 2:
        continue
    a = {n: roc_auc_score(yte[s], p[s]) for n, p in preds.items()}
    for n, v in a.items():
        boot[n].append(v)
    for n in diff:
        diff[n].append(a[n] - a['VQC (ours)'])

print(f'\n95% CI per model, {B} paired bootstrap resamples of the 946 held-out rows:')
for n in preds:
    v = np.array(boot[n])
    lo, hi = np.percentile(v, [2.5, 97.5])
    print(f'  {n:24} {roc_auc_score(yte, preds[n]):.4f}  [{lo:.4f}, {hi:.4f}]  width {hi-lo:.4f}')

print('\nPAIRED difference vs our VQC (the question that matters):')
out = {}
for n in diff:
    v = np.array(diff[n])
    lo, hi = np.percentile(v, [2.5, 97.5])
    p_over = float((v <= 0).mean())
    sig = 'RESOLVED (CI excludes 0)' if lo > 0 else 'NOT RESOLVED (CI includes 0)'
    print(f'  {n:24} +{v.mean():.4f}  [{lo:+.4f}, {hi:+.4f}]  '
          f'VQC wins in {p_over*100:.1f}% of resamples  -> {sig}')
    out[n] = dict(mean=round(float(v.mean()),4), lo=round(float(lo),4),
                  hi=round(float(hi),4), vqc_wins_pct=round(p_over*100,1),
                  resolved=bool(lo > 0))
json.dump(out, open(os.path.join(API, 'bootstrap_gap.json'), 'w'), indent=2)
print('\nwrote bootstrap_gap.json')
