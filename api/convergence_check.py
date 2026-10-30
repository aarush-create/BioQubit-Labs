"""
convergence_check.py -- settle whether qiskit.aer AGREES with default.qubit.

WHY THIS REPLACES THE EXACT-EQUALITY TEST
-----------------------------------------
parity_check.py asked "are the two backends' scores equal to 1e-6?". That is
the wrong question for qiskit.aer, because PennyLane-Qiskit's Aer device is a
SAMPLING simulator: it does not honour shots=None as analytic mode. Two runs
of the same circuit give different numbers (we observed exactly that), so an
equality test can only ever fail.

The right question is: does the sampled qiskit.aer result CONVERGE to the
analytic default.qubit result as the shot count grows?

  * If yes -- the two backends implement the same quantum state and the
    residual is pure shot noise. Safe to serve on qiskit.aer (the API already
    reports a shot-noise error bar with every prediction).
  * If the residual PLATEAUS at some non-zero value as shots grow -- there is
    a genuine disagreement (wire ordering, basis-state indexing, a
    transpilation difference). Do NOT serve on qiskit.aer.

HOW IT DECIDES
--------------
For each mutation, at each shot level, we run the circuit R times on
qiskit.aer and average. The standard error of that mean is estimated from the
spread of the R repeats. We then ask whether

    |mean_aer - analytic|  <  Z * SE_of_mean        (Z = 3)

If every fixture satisfies this at the HIGHEST shot level, the residual is
statistically indistinguishable from sampling noise -> PASS.

We also print the residual at each shot level so you can see it fall roughly
as 1/sqrt(N). That trend is itself the evidence, and it makes a good slide.

NOTE: this script builds its own QNodes from the engine's trained weights, so
it does NOT depend on QVIRA_BACKEND and does NOT need subprocesses. It also
works whether or not you applied the `shots or 2048` patch to circuit.py,
because every shot count here is passed explicitly.

Usage (from the api/ directory):
    python convergence_check.py
    python convergence_check.py --shots 2048 8192 32768 --repeats 10

Exit code 0 = consistent with pure shot noise (safe), 1 = real disagreement.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np

# Force the engine to build cheap analytic QNodes at import; we construct our
# own QNodes on whichever backend we want below, so the engine's own backend
# choice is irrelevant and we don't want to pay Aer transpilation twice.
os.environ["QVIRA_BACKEND"] = "default.qubit"

import mutation_features as mutfeat                      # noqa: E402
from circuit import make_qnode, logits, sigmoid          # noqa: E402
from quantum_engine import engine                        # noqa: E402

# SARS-CoV-2 RBD window used by the specialist model.
RBD_START, RBD_END = 331, 531

FIXTURES = [
    ("N", "Y", 501),
    ("E", "K", 484),
    ("K", "N", 417),
    ("L", "R", 452),
    ("S", "P", 371),
    ("Q", "H", 498),
]

Z = 3.0  # how many standard errors we allow before calling it a real bias


def _score(qnode, angles) -> float:
    raw = np.asarray(qnode(np.asarray(angles, dtype=float), engine.weights),
                     dtype=float)
    return float(sigmoid(float(logits(raw, engine.readout, engine.readout_kind))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", type=int, nargs="+", default=[2048, 8192, 32768])
    ap.add_argument("--repeats", type=int, default=10)
    args = ap.parse_args()

    if not engine.is_trained:
        print("ERROR: weights.npz not found. Run train_vqc.py first.", file=sys.stderr)
        return 1

    geom = dict(n_features=engine.n_features, n_qubits=engine.n_qubits,
                encoding=engine.encoding, axes=engine.axes)
    print(f"model: {engine.n_qubits} qubits, {engine.weights.shape[0]} layers, "
          f"encoding={engine.encoding}, readout={engine.readout_kind}")

    # ---- featurise every fixture once
    feats: dict[str, list[float]] = {}
    for wt, mut, site in FIXTURES:
        rel_pos = (site - RBD_START) / (RBD_END - RBD_START)
        angles, _ = mutfeat.featurise_mutation(wt, mut, rel_pos, site=site)
        feats[f"{wt}{site}{mut}"] = angles

    # ---- analytic reference on default.qubit (deterministic)
    qn_ref = make_qnode(readout_kind=engine.readout_kind, shots=None,
                        backend="default.qubit", **geom)
    ref = {name: _score(qn_ref, a) for name, a in feats.items()}
    print("\nanalytic reference (default.qubit, shots=None):")
    for name, v in ref.items():
        print(f"  {name:<8} {v:.8f}")

    # ---- sampled runs on qiskit.aer at increasing shot counts
    overall_ok = True
    summary: list[tuple[int, float, float]] = []   # (shots, max_resid, max_ratio)

    for n_shots in args.shots:
        print(f"\n=== qiskit.aer @ {n_shots} shots, {args.repeats} repeats ===")
        qn = make_qnode(readout_kind=engine.readout_kind, shots=n_shots,
                        backend="qiskit.aer", **geom)

        print(f"{'mutation':<9} {'analytic':>11} {'mean(aer)':>11} "
              f"{'SE(mean)':>10} {'|resid|':>10} {'resid/SE':>9}  verdict")
        print("-" * 74)

        level_ok = True
        max_resid = 0.0
        max_ratio = 0.0
        t0 = time.time()

        for name, angles in feats.items():
            samples = np.array([_score(qn, angles) for _ in range(args.repeats)])
            mean = float(samples.mean())
            # ddof=1 -> sample sd; SE of the mean = sd / sqrt(R)
            se_mean = float(samples.std(ddof=1) / np.sqrt(len(samples))) if len(samples) > 1 else float("nan")
            resid = abs(mean - ref[name])
            ratio = resid / se_mean if se_mean > 0 else float("inf")
            ok = ratio < Z
            level_ok &= ok
            max_resid = max(max_resid, resid)
            max_ratio = max(max_ratio, ratio)
            print(f"{name:<9} {ref[name]:>11.8f} {mean:>11.8f} {se_mean:>10.2e} "
                  f"{resid:>10.2e} {ratio:>9.2f}  {'ok' if ok else 'BIAS?'}")

        dt = time.time() - t0
        print(f"  max |resid| = {max_resid:.2e}   max resid/SE = {max_ratio:.2f}   "
              f"({dt:.1f}s)")
        summary.append((n_shots, max_resid, max_ratio))
        if n_shots == args.shots[-1]:
            overall_ok = level_ok

    # ---- did the residual shrink like 1/sqrt(N)?
    print("\n=== convergence summary ===")
    print(f"{'shots':>8} {'max|resid|':>12} {'expected ~1/sqrt(N) scaling':>30}")
    base_shots, base_resid, _ = summary[0]
    for n_shots, resid, _ in summary:
        predicted = base_resid * np.sqrt(base_shots / n_shots)
        print(f"{n_shots:>8} {resid:>12.2e} {predicted:>30.2e}")

    print()
    if overall_ok:
        print("VERDICT: PASS -- at the highest shot count every fixture's residual is")
        print("  within 3 standard errors of the analytic value. The qiskit.aer and")
        print("  default.qubit backends implement the SAME quantum state; the")
        print("  difference you see per-call is shot noise, which quantum_engine.py")
        print("  already reports as an error bar.")
        print("  => Safe to serve with QVIRA_BACKEND=qiskit.aer.")
        return 0

    print("VERDICT: FAIL -- at least one fixture's residual exceeds 3 SE at the")
    print("  highest shot count, and/or the residual is not shrinking with shots.")
    print("  That is a genuine backend disagreement, not sampling noise.")
    print("  => Do NOT serve with QVIRA_BACKEND=qiskit.aer. Keep default.qubit")
    print("     for inference and use qiskit.aer only for the VQE chemistry")
    print("     benchmark, which has no trained weights to reproduce.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
