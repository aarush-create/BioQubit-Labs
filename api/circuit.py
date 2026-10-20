"""
circuit.py -- ONE definition of the ansatz, encoding and readout, imported by
train_vqc.py, quantum_engine.py and bootstrap_gap.py.

WHY THIS FILE EXISTS
--------------------
The ansatz used to be written out separately in each file, with a comment
saying "must stay identical to quantum_engine.py". That is a drift waiting to
happen: train one circuit, serve another, and the served scores are silently
wrong. One source of truth now.

------------------------------------------------------------------------------
ENCODING  (the reason this file grew)
------------------------------------------------------------------------------
`angle`  one feature per qubit, RY only.
         n_qubits == n_features, forced. This is the original.

`dense`  several features per qubit, one per rotation axis.
         n_qubits == ceil(n_features / len(axes)).
         With axes ("Y","Z") six features need THREE qubits, not six.

WHY DENSE EXISTS, measured not assumed:

  1. 200 PAIRED site-grouped resamples of the development set (identical splits
     scored with both feature sets) show six descriptors beat the shipped four:
     0.7790 +/- 0.049 against 0.7551 +/- 0.046, a paired difference of +0.0239
     winning 173 of 200 draws, paired t = +14.5. So there IS signal in
     descriptors we previously dropped.

     The two added descriptors are wt_hydropathy and delta_hydropathy. Note the
     per-draw 95% range of the difference is [-0.040, +0.054] and so includes
     zero: on any ONE split six features can lose. That is exactly why the
     comparison is paired over many draws rather than read off a single split,
     which is how the earlier "fewer features win" claim arose.

  2. Under `angle`, six descriptors would force six qubits. Our own ablations
     measured what width costs: 8 qubits scored 0.640, and 8 qubits with 6
     layers collapsed to 0.558 with the training loss never falling below
     0.556 -- a barren plateau. Width is the thing that breaks training here.

  3. `dense` decouples the two. Six descriptors on three qubits is NARROWER
     than the shipped model while carrying more information.

So the point of dense encoding is not elegance; it is that the feature set we
measured to be better is unreachable without it.

ORDERING, and why it matters more than it looks
-----------------------------------------------
Features are assigned axis-major: feature 0 -> qubit 0 RY, feature 1 -> qubit 1
RY, ... then wrapping onto the next axis. Two consequences, both deliberate:

  * The earliest (most informative) features land on DIFFERENT qubits rather
    than stacking on qubit 0.
  * Every qubit receives its RY before its RZ. RZ applied to |0> changes only an
    unobservable global phase, so an RZ-first ordering silently discards those
    features. Verified by direct statevector simulation: with axes ordered
    ("Z","Y"), perturbing the three Z-carried features changes the output
    distribution by max|dP| = 1e-16, i.e. not at all. With ("Y","X") ordering
    the same perturbation moves it by 0.99.

HOW PHASE-ENCODED FEATURES BECOME MEASURABLE (and the depth they need)
----------------------------------------------------------------------
With the `probs` readout we measure in the computational basis, where a pure
phase is invisible. The thing that makes RZ-encoded features readable is NOT
the CNOT ring -- CNOTs permute basis states, so they move amplitudes around
without converting phase into population. Verified: encoding followed by a
CNOT ring alone leaves the RZ features completely dead (max|dP| = 0.0).

What does the work is the RY inside each `Rot(phi, theta, omega)` of
StronglyEntanglingLayers, which rotates relative phase into amplitude. With the
full ansatz, all six features are live. Measured per-feature sensitivity
(max|dP| for a +0.9 rad perturbation, 3 qubits, 6 features):

    axes ("Y","Z"), 1 layer : 0.209 0.107 0.033 0.031 0.208 0.059
    axes ("Y","Z"), 6 layers: 0.195 0.154 0.156 0.190 0.184 0.298
    axes ("Y","X"), 6 layers: 0.312 0.236 0.246 0.228 0.167 0.357
    angle, 4 features/4 qubits, 6 layers: 0.149 0.103 0.093 0.110

Two things follow. At ONE layer the phase-carried features are nearly
invisible (0.03), so dense encoding with a phase axis REQUIRES depth -- it is
not a drop-in at shallow depth. At six layers, which is what we ship, every
feature is live and sensitivity is HIGHER than the current angle encoding.

Encoding, depth and readout are therefore not independent choices here, and
`axes=("Y","X")` is offered because RX changes amplitudes directly and so does
not depend on depth in the same way.

------------------------------------------------------------------------------
READOUT
------------------------------------------------------------------------------
`single_z`  p = sigmoid(w <Z_0> + b).  Measures ONE qubit. 2 parameters.
`probs`     p = sigmoid(sum_k w_k P(k) + b) over all 2^n basis outcomes.
            Spans the same function space as a linear combination of every
            Z-type Pauli correlator, because the basis probabilities are the
            Walsh-Hadamard transform of those correlators. 2^n + 1 parameters.
            Also maps directly onto a Qiskit SamplerV2 result, so a hardware
            port needs no change to the readout maths.

The quantum circuit is identical for both, so an ablation between them isolates
the readout.
"""

from __future__ import annotations

import math

import pennylane as qml
from pennylane import numpy as pnp

READOUT_KINDS = ("single_z", "probs")
ENCODINGS = ("angle", "dense")
DEFAULT_AXES = ("Y", "Z")

_ROT = {"X": qml.RX, "Y": qml.RY, "Z": qml.RZ}


# ---------------------------------------------------------------- geometry
def qubits_needed(n_features: int, encoding: str = "dense",
                  axes: tuple[str, ...] = DEFAULT_AXES) -> int:
    """How many wires this many features require under a given encoding."""
    if encoding == "angle":
        return int(n_features)
    if encoding == "dense":
        return int(math.ceil(n_features / float(len(axes))))
    raise ValueError(f"unknown encoding {encoding!r}")


def capacity(n_qubits: int, encoding: str = "dense",
             axes: tuple[str, ...] = DEFAULT_AXES) -> int:
    """How many features fit on this many wires."""
    if encoding == "angle":
        return int(n_qubits)
    if encoding == "dense":
        return int(n_qubits * len(axes))
    raise ValueError(f"unknown encoding {encoding!r}")


def n_readout_params(n_qubits: int, readout_kind: str) -> int:
    if readout_kind == "single_z":
        return 2
    if readout_kind == "probs":
        return 2 ** n_qubits + 1
    raise ValueError(f"unknown readout kind {readout_kind!r}")


# ---------------------------------------------------------------- encoding
def _encode(features, n_features: int, n_qubits: int, encoding: str,
            axes: tuple[str, ...]) -> None:
    """Write the features onto the register. See ORDERING above."""
    if encoding == "angle":
        qml.AngleEmbedding(features=features, wires=range(n_qubits),
                           rotation="Y")
        return

    k = 0
    for ax in axes:                       # axis-major: RY on all wires first
        gate = _ROT[ax]
        for w in range(n_qubits):
            if k >= n_features:
                return
            # features[..., k] keeps the leading batch dimension when present,
            # so PennyLane's parameter broadcasting still applies.
            gate(features[..., k], wires=w)
            k += 1


def _ansatz(features, weights, n_features: int, n_qubits: int,
            encoding: str, axes: tuple[str, ...]) -> None:
    """Data re-uploading (Perez-Salinas et al. 2020): the input is re-encoded
    before EVERY entangling layer, which makes the circuit a universal
    approximator rather than a fixed feature map followed by rotations."""
    for layer in range(weights.shape[0]):
        _encode(features, n_features, n_qubits, encoding, axes)
        qml.StronglyEntanglingLayers(weights[layer:layer + 1],
                                     wires=range(n_qubits))


def make_qnode(n_features: int, n_qubits: int | None = None,
               readout_kind: str = "probs", encoding: str = "angle",
               axes: tuple[str, ...] = DEFAULT_AXES,
               shots: int | None = None, backend: str = "default.qubit"):
    """Build the QNode.

    n_qubits defaults to the minimum the encoding requires. Passing a larger
    value is allowed (the spare wires start in |0> and are still entangled);
    passing a smaller one is an error rather than a silent truncation, because
    dropping features quietly is exactly the kind of bug that produces a
    plausible-looking wrong number.

    shots=None is analytic; an int samples, which is how a real shot-noise
    error bar gets reported instead of implying infinite precision.
    """
    if readout_kind not in READOUT_KINDS:
        raise ValueError(f"unknown readout kind {readout_kind!r}")
    if encoding not in ENCODINGS:
        raise ValueError(f"unknown encoding {encoding!r}")
    for ax in axes:
        if ax not in _ROT:
            raise ValueError(f"unknown rotation axis {ax!r}")

    need = qubits_needed(n_features, encoding, axes)
    if n_qubits is None:
        n_qubits = need
    if n_qubits < need:
        raise ValueError(
            f"{n_features} features need at least {need} qubits under "
            f"encoding={encoding!r} with axes={axes}, but n_qubits={n_qubits} "
            f"was requested. Features would be silently dropped."
        )
    if encoding == "angle" and n_qubits != n_features:
        raise ValueError(
            f"encoding='angle' puts one feature per wire, so n_qubits must "
            f"equal n_features ({n_features}), not {n_qubits}. Use "
            f"encoding='dense' to carry more features than wires."
        )

    if backend == "qiskit.aer":
        dev = qml.device("qiskit.aer", wires=n_qubits, shots=shots or 2048)
    else:
        dev = qml.device(backend, wires=n_qubits, shots=shots)

    if readout_kind == "single_z":
        @qml.qnode(dev)
        def qnode(features, weights):
            _ansatz(features, weights, n_features, n_qubits, encoding, axes)
            return qml.expval(qml.PauliZ(0))
    else:
        @qml.qnode(dev)
        def qnode(features, weights):
            _ansatz(features, weights, n_features, n_qubits, encoding, axes)
            return qml.probs(wires=range(n_qubits))

    qnode.n_features = n_features
    qnode.n_qubits = n_qubits
    qnode.encoding = encoding
    qnode.axes = tuple(axes)
    qnode.readout_kind = readout_kind
    return qnode


# ---------------------------------------------------------------- readout
def logits(raw, readout, readout_kind: str):
    """Circuit output -> logit.

    Shapes for a batch of B inputs on n qubits:
        single_z   raw (B,)        readout (2,)
        probs      raw (B, 2**n)   readout (2**n + 1,)
    A single un-batched input drops the leading B and still works.

    pennylane.numpy throughout, so this is differentiable during training and
    plain-numeric at inference.
    """
    if readout_kind == "single_z":
        return readout[0] * raw + readout[1]
    return pnp.sum(raw * readout[:-1], axis=-1) + readout[-1]


def sigmoid(x):
    return 1.0 / (1.0 + pnp.exp(-x))


def predict_proba(raw, readout, readout_kind: str):
    return sigmoid(logits(raw, readout, readout_kind))


def init_readout(n_qubits: int, readout_kind: str, rng=None):
    """Initial readout parameters.

    single_z starts at the original (scale=1, bias=0).

    probs starts SMALL and RANDOM, not at zero. All-zero weights give an
    identically-zero logit, so every sample scores 0.5 AND the gradient with
    respect to the circuit parameters vanishes -- the circuit would not train at
    all on the first steps. Small random values break that symmetry. The bias
    starts at zero and lets the data set the base rate.
    """
    if readout_kind == "single_z":
        return pnp.array([1.0, 0.0], requires_grad=True)

    d = 2 ** n_qubits
    if rng is None:
        import numpy as _np
        rng = _np.random.default_rng(0)
    w = rng.normal(0.0, 0.1, d + 1)
    w[-1] = 0.0
    return pnp.array(w, requires_grad=True)
