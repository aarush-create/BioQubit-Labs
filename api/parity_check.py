"""
parity_check.py -- confirm the Qiskit-Aer backend produces the SAME scores
as the shipped PennyLane default.qubit backend on identical weights.

Run from the api/ directory (same place as quantum_engine.py). Scores a set
of mutations under BOTH backends in analytic mode (shots=None) and asserts
|Δ score| < 1e-6. Analytic mode is the honest check: with sampling, there's
real shot noise and the test would be about the error-bar size, not parity.

Why in two subprocesses: quantum_engine.py reads QVIRA_BACKEND once at import
time, so changing the env var in a single process has no effect. Running each
backend in a fresh subprocess guarantees the env var is read correctly.

Usage:
    cd api
    python parity_check.py

Exit code 0 on parity, 1 on mismatch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

# A handful of SARS-CoV-2 RBD mutations spanning different sites and chemistry.
# Add more to catch edge cases if you've extended the featuriser.
FIXTURES = [
    # (wt_aa, mut_aa, site)      RBD window is 331-531.
    ("N", "Y", 501),   # the headline Alpha/Omicron variant
    ("E", "K", 484),   # Beta-defining
    ("K", "N", 417),   # Beta/Omicron
    ("L", "R", 452),   # Delta
    ("S", "P", 371),   # Omicron
    ("Q", "H", 498),   # Omicron
]

# How this process should behave: either SCORE under the backend named in the
# env var, or ORCHESTRATE two score-children and compare.
MODE_SCORE = os.getenv("QVIRA_PARITY_MODE") == "score"

if MODE_SCORE:
    # Child process: load engines under whatever QVIRA_BACKEND was set,
    # score every fixture analytically, print one JSON row per mutation.
    import mutation_features as mutfeat
    from quantum_engine import engine

    assert engine.is_trained, (
        "weights.npz not found — run train_vqc.py first. "
        "parity_check needs a trained model."
    )

    rows = []
    for wt, mut, site in FIXTURES:
        rel_pos = (site - 331) / (531 - 331)
        angles, explain = mutfeat.featurise_mutation(wt, mut, rel_pos, site=site)
        # with_error_bar=False keeps the call analytic (no shot sampling).
        res = engine.score(angles, with_error_bar=False)
        rows.append({
            "mutation": f"{wt}{site}{mut}",
            "score": res["threat_score"],
            "backend": res["backend"],
        })
    # Prefix with a sentinel so the parent can find this line even if other
    # imports print to stdout.
    print("###PARITY_JSON###" + json.dumps(
        {"rows": rows, "backend": rows[0]["backend"]}))
    sys.exit(0)


# Orchestrator path: spawn one child per backend, diff the scores.

_SENTINEL = "###PARITY_JSON###"


def _run(backend: str) -> dict:
    env = os.environ.copy()
    env["QVIRA_BACKEND"] = backend
    env["QVIRA_PARITY_MODE"] = "score"
    # Make sure the child can import quantum_engine / mutation_features from
    # the api/ directory. Not using python -I because -I implies -P on 3.11+,
    # which strips the script directory from sys.path and breaks the imports.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env["PYTHONPATH"] = script_dir + os.pathsep + env.get("PYTHONPATH", "")

    out = subprocess.run(
        [sys.executable, __file__],
        env=env, capture_output=True, text=True,
    )
    if out.returncode != 0:
        print(f"\n[parity_check] child for backend={backend!r} exited with "
              f"status {out.returncode}", file=sys.stderr)
        print("---- child stdout ----", file=sys.stderr)
        print(out.stdout, file=sys.stderr)
        print("---- child stderr ----", file=sys.stderr)
        print(out.stderr, file=sys.stderr)
        raise RuntimeError(f"backend {backend!r} failed; see above")

    # Child prints a sentinel-prefixed JSON line; find it. (A noisy library
    # could sprinkle other lines on stdout, so last-line was fragile.)
    for line in out.stdout.splitlines():
        if line.startswith(_SENTINEL):
            return json.loads(line[len(_SENTINEL):])
    print("[parity_check] no sentinel line found. Child stdout was:\n"
          + out.stdout, file=sys.stderr)
    raise RuntimeError(f"no parity JSON from backend={backend}")


def main() -> int:
    print("Scoring fixtures under default.qubit ...")
    a = _run("default.qubit")
    print("Scoring fixtures under qiskit.aer ...")
    b = _run("qiskit.aer")
    assert len(a["rows"]) == len(b["rows"])

    print(f"\n{'mutation':<10}  {'default.qubit':>13}  {'qiskit.aer':>13}  {'|Δ|':>10}")
    print("-" * 54)
    worst = 0.0
    for ra, rb in zip(a["rows"], b["rows"]):
        assert ra["mutation"] == rb["mutation"]
        d = abs(ra["score"] - rb["score"])
        worst = max(worst, d)
        print(f"{ra['mutation']:<10}  {ra['score']:>13.8f}  {rb['score']:>13.8f}  {d:>10.2e}")

    tol = 1e-6
    print(f"\nworst |Δ| = {worst:.2e}  (tolerance {tol:.0e})")
    if worst < tol:
        print("PARITY OK — qiskit.aer agrees with default.qubit on every fixture.")
        return 0
    print("PARITY FAILED — backends disagree. DO NOT ship with QVIRA_BACKEND=qiskit.aer.")
    print("Likely causes: wire-ordering convention mismatch in a readout; different "
          "basis-state indexing between qml.probs on the two devices.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
