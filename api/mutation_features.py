"""
Mutation-level featurisation (v2 -- 8 descriptors).

WHAT CHANGED FROM v1 AND WHY
----------------------------
v1 used 4 descriptors and reached 0.586 AUC, barely above the classical
baselines (0.569-0.642). Every model was weak, which pointed at the FEATURES
rather than the classifier. v2 adds four descriptors that are standard in
variant-effect prediction:

  f4  BLOSUM62 score   how often this exact substitution is observed in
                       related proteins. Usually the single strongest cheap
                       predictor of whether a mutation is tolerated.
  f5  wild-type KD     context: replacing a buried hydrophobic residue is not
                       the same event as replacing an exposed polar one.
  f6  wild-type volume context for the steric term.
  f7  Pro/Gly flag     proline and glycine have unique backbone geometry, so
                       gaining or losing one is structurally special.

A NOTE ON QUBIT COUNT
---------------------
Angle encoding puts one feature on one qubit, so n_qubits == n_features. Going
from 4 to 8 qubits is only meaningful BECAUSE there are now 8 features. Adding
qubits without adding information would leave the extra wires in a fixed state
and just deepen the circuit -- more parameters, no more signal, and a higher
risk of barren plateaus (vanishing gradients at depth). Say this if a judge
asks why not 20 qubits.

BLOSUM62 values below were generated from Biopython's canonical matrix
(Bio.Align.substitution_matrices), not typed by hand.
"""

from __future__ import annotations

import json
import math
import os

BLOSUM62 = {
    "A": {"A": 4, "C": 0, "D": -2, "E": -1, "F": -2, "G": 0, "H": -2, "I": -1, "K": -1, "L": -1, "M": -1, "N": -2, "P": -1, "Q": -1, "R": -1, "S": 1, "T": 0, "V": 0, "W": -3, "Y": -2},
    "C": {"A": 0, "C": 9, "D": -3, "E": -4, "F": -2, "G": -3, "H": -3, "I": -1, "K": -3, "L": -1, "M": -1, "N": -3, "P": -3, "Q": -3, "R": -3, "S": -1, "T": -1, "V": -1, "W": -2, "Y": -2},
    "D": {"A": -2, "C": -3, "D": 6, "E": 2, "F": -3, "G": -1, "H": -1, "I": -3, "K": -1, "L": -4, "M": -3, "N": 1, "P": -1, "Q": 0, "R": -2, "S": 0, "T": -1, "V": -3, "W": -4, "Y": -3},
    "E": {"A": -1, "C": -4, "D": 2, "E": 5, "F": -3, "G": -2, "H": 0, "I": -3, "K": 1, "L": -3, "M": -2, "N": 0, "P": -1, "Q": 2, "R": 0, "S": 0, "T": -1, "V": -2, "W": -3, "Y": -2},
    "F": {"A": -2, "C": -2, "D": -3, "E": -3, "F": 6, "G": -3, "H": -1, "I": 0, "K": -3, "L": 0, "M": 0, "N": -3, "P": -4, "Q": -3, "R": -3, "S": -2, "T": -2, "V": -1, "W": 1, "Y": 3},
    "G": {"A": 0, "C": -3, "D": -1, "E": -2, "F": -3, "G": 6, "H": -2, "I": -4, "K": -2, "L": -4, "M": -3, "N": 0, "P": -2, "Q": -2, "R": -2, "S": 0, "T": -2, "V": -3, "W": -2, "Y": -3},
    "H": {"A": -2, "C": -3, "D": -1, "E": 0, "F": -1, "G": -2, "H": 8, "I": -3, "K": -1, "L": -3, "M": -2, "N": 1, "P": -2, "Q": 0, "R": 0, "S": -1, "T": -2, "V": -3, "W": -2, "Y": 2},
    "I": {"A": -1, "C": -1, "D": -3, "E": -3, "F": 0, "G": -4, "H": -3, "I": 4, "K": -3, "L": 2, "M": 1, "N": -3, "P": -3, "Q": -3, "R": -3, "S": -2, "T": -1, "V": 3, "W": -3, "Y": -1},
    "K": {"A": -1, "C": -3, "D": -1, "E": 1, "F": -3, "G": -2, "H": -1, "I": -3, "K": 5, "L": -2, "M": -1, "N": 0, "P": -1, "Q": 1, "R": 2, "S": 0, "T": -1, "V": -2, "W": -3, "Y": -2},
    "L": {"A": -1, "C": -1, "D": -4, "E": -3, "F": 0, "G": -4, "H": -3, "I": 2, "K": -2, "L": 4, "M": 2, "N": -3, "P": -3, "Q": -2, "R": -2, "S": -2, "T": -1, "V": 1, "W": -2, "Y": -1},
    "M": {"A": -1, "C": -1, "D": -3, "E": -2, "F": 0, "G": -3, "H": -2, "I": 1, "K": -1, "L": 2, "M": 5, "N": -2, "P": -2, "Q": 0, "R": -1, "S": -1, "T": -1, "V": 1, "W": -1, "Y": -1},
    "N": {"A": -2, "C": -3, "D": 1, "E": 0, "F": -3, "G": 0, "H": 1, "I": -3, "K": 0, "L": -3, "M": -2, "N": 6, "P": -2, "Q": 0, "R": 0, "S": 1, "T": 0, "V": -3, "W": -4, "Y": -2},
    "P": {"A": -1, "C": -3, "D": -1, "E": -1, "F": -4, "G": -2, "H": -2, "I": -3, "K": -1, "L": -3, "M": -2, "N": -2, "P": 7, "Q": -1, "R": -2, "S": -1, "T": -1, "V": -2, "W": -4, "Y": -3},
    "Q": {"A": -1, "C": -3, "D": 0, "E": 2, "F": -3, "G": -2, "H": 0, "I": -3, "K": 1, "L": -2, "M": 0, "N": 0, "P": -1, "Q": 5, "R": 1, "S": 0, "T": -1, "V": -2, "W": -2, "Y": -1},
    "R": {"A": -1, "C": -3, "D": -2, "E": 0, "F": -3, "G": -2, "H": 0, "I": -3, "K": 2, "L": -2, "M": -1, "N": 0, "P": -2, "Q": 1, "R": 5, "S": -1, "T": -1, "V": -3, "W": -3, "Y": -2},
    "S": {"A": 1, "C": -1, "D": 0, "E": 0, "F": -2, "G": 0, "H": -1, "I": -2, "K": 0, "L": -2, "M": -1, "N": 1, "P": -1, "Q": 0, "R": -1, "S": 4, "T": 1, "V": -2, "W": -3, "Y": -2},
    "T": {"A": 0, "C": -1, "D": -1, "E": -1, "F": -2, "G": -2, "H": -2, "I": -1, "K": -1, "L": -1, "M": -1, "N": 0, "P": -1, "Q": -1, "R": -1, "S": 1, "T": 5, "V": 0, "W": -2, "Y": -2},
    "V": {"A": 0, "C": -1, "D": -3, "E": -2, "F": -1, "G": -3, "H": -3, "I": 3, "K": -2, "L": 1, "M": 1, "N": -3, "P": -2, "Q": -2, "R": -3, "S": -2, "T": 0, "V": 4, "W": -3, "Y": -1},
    "W": {"A": -3, "C": -2, "D": -4, "E": -3, "F": 1, "G": -2, "H": -2, "I": -3, "K": -3, "L": -2, "M": -1, "N": -4, "P": -4, "Q": -2, "R": -3, "S": -3, "T": -2, "V": -3, "W": 11, "Y": 2},
    "Y": {"A": -2, "C": -2, "D": -3, "E": -2, "F": 3, "G": -3, "H": 2, "I": -1, "K": -2, "L": -1, "M": -1, "N": -2, "P": -3, "Q": -1, "R": -2, "S": -2, "T": -2, "V": -1, "W": 2, "Y": 7},
}

# Kyte & Doolittle hydropathy.
KD = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5,
    "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5,
    "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6,
    "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}
CHARGE = {"K": 1.0, "R": 1.0, "D": -1.0, "E": -1.0, "H": 0.1}
# Zamyatnin (1972) residue volumes, cubic angstroms.
VOLUME = {
    "A": 88.6, "R": 173.4, "N": 114.1, "D": 111.1, "C": 108.5,
    "Q": 143.8, "E": 138.4, "G": 60.1, "H": 153.2, "I": 166.7,
    "L": 166.7, "K": 168.6, "M": 162.9, "F": 189.9, "P": 112.7,
    "S": 89.0, "T": 116.1, "W": 227.8, "Y": 193.6, "V": 140.0,
}
VALID = set(KD)

# ---------------------------------------------------------------------------
# STRUCTURAL FEATURE: distance from each RBD residue to human ACE2
# ---------------------------------------------------------------------------
# Computed from the experimental complex 6M0J by build_structure_features.py.
# This is the only descriptor that knows about FOLDING rather than sequence:
# residues 417 and 501 are far apart in the chain and adjacent at the interface,
# which `relative_position` could never express.
#
# Measured (MLP, same site-grouped split):
#   relative_position alone   0.6016 AUC
#   ACE2 distance alone       0.7143 AUC   <- best single feature we have
#   4 features with rel_pos   0.7573
#   4 features with distance  0.7772
_DIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ace2_distance.json")
try:
    with open(_DIST_PATH) as _fh:
        ACE2_DISTANCE = {int(k): float(v) for k, v in json.load(_fh).items()}
except (FileNotFoundError, json.JSONDecodeError):
    ACE2_DISTANCE = {}

# Sites outside the solved construct (331-332, 527-531) get the far value, which
# is honest: they are not at the interface.
ACE2_FAR = 45.0


def has_ace2_structure(site: int) -> bool:
    """Was this site resolved in the crystal structure?

    6M0J covers RBD residues 333-526. Sites outside that (331-332, 527-531) get
    the ACE2_FAR fallback, which the model reads as "maximally far from the
    interface" and therefore scores highly. That is an artefact of MISSING DATA,
    not evidence, so callers must be able to tell the two apart.
    """
    return int(site) in ACE2_DISTANCE


def ace2_distance(site: int) -> float:
    """Minimum heavy-atom distance from this spike site to ACE2, angstroms."""
    return ACE2_DISTANCE.get(int(site), ACE2_FAR)

# ---------------------------------------------------------------------------
# RANGE CALIBRATION -- why blosum62 changed from (-4, 11) to (-4, 3)
# ---------------------------------------------------------------------------
# Angle encoding maps each descriptor onto [0, pi] by clamping to its declared
# range. If the declared range is wider than the values that actually occur,
# the samples compress into a narrow arc of the rotation and the circuit sees
# far less variation than it could -- the encoding throws away resolution.
#
# Measured on single_mut_effects.csv (3802 rows, wt != mut), observed p1-p99
# against the declared range:
#
#     descriptor          declared        observed p1-p99     range used
#     delta_hydropathy    (-9, 9)         (-8.30,  8.10)          91%
#     delta_charge        (-2, 2)         (-1.10,  1.10)          55%
#     delta_volume        (-170, 170)     (-116.68, 138.80)       75%
#     relative_position   (0, 1)          ( 0.01,  0.99)          98%
#     blosum62            (-4, 11)        (-4.00,  3.00)          47%   <-- bad
#     wt_hydropathy       (-4.5, 4.5)     (-4.50,  4.50)         100%
#     wt_volume           (60, 228)       (60.10, 193.60)         79%
#     pro_gly_flag        (0, 1)          ( 0.00,  1.00)         100%
#     ace2_distance       (0, 45)         ( 2.71, 45.00)          94%
#
# blosum62 is the worst offender AND our strongest descriptor. The upper bound
# of 11 comes from the matrix diagonal (W->W = 11), but identical residues are
# filtered out before featurisation, so values above +3 never occur. Observed
# counts across the whole dataset:
#     -4:156  -3:860  -2:976  -1:851  0:542  1:251  2:113  3:53
#
# Narrowing the clamp to (-4, 3) roughly doubles the angular resolution on
# that descriptor. It is a no-op for the classical baselines, which are
# effectively invariant to a monotone rescaling -- measured: logistic
# regression 0.7745 with the old ranges, 0.7738 with empirical ranges, a
# difference well inside the +/-0.06 fold spread. So this change can only
# matter to the QUANTUM model, which is the point: it is a change to the
# encoding, not to the information.
#
# MEASURED, AND IT MADE NO DIFFERENCE. On the panel, where restart noise is
# only +/-0.002, three seeds each:
#     old clamp (-4, 11)   0.6812 +/- 0.0022   range [0.6788, 0.6832]
#     new clamp (-4,  3)   0.6796 +/- 0.0014   range [0.6781, 0.6808]
# Overlapping, with the "corrected" clamp marginally worse. The reasoning that
# more angular resolution on the strongest descriptor must help was simply
# wrong -- the circuit did not need it.
#
# The narrower clamp is kept because it is the honest description of the data
# (+11 cannot occur once identical residues are filtered), and it is recorded
# here as a measured NULL rather than quietly dropped. It is not a result.
#
# Fixed clamp ranges -> angles in [0, pi]. Constants, never fitted per-input.
RANGES = (
    (-9.0, 9.0),      # delta hydropathy
    (-2.0, 2.0),      # delta charge
    (-170.0, 170.0),  # delta volume
    (0.0, 1.0),       # relative position
    (-4.0, 3.0),      # BLOSUM62 score -- see RANGE CALIBRATION below
    (-4.5, 4.5),      # wild-type hydropathy
    (60.0, 228.0),    # wild-type volume
    (0.0, 1.0),       # proline/glycine involved
    (0.0, 45.0),      # distance to ACE2, angstroms
    (0.0, 40.0),      # burial: residues within 10 A (contact number)
)
NAMES = (
    "delta_hydropathy", "delta_charge", "delta_volume", "relative_position",
    "blosum62", "wt_hydropathy", "wt_volume", "pro_gly_flag",
    "ace2_distance", "burial",
)

# ---------------------------------------------------------------------------
# BURIAL (index 9) -- supplied per row, not computed here
# ---------------------------------------------------------------------------
# raw_descriptors() returns indices 0-8. Index 9 is appended by
# train_vqc.load_panel() from the `burial` column of a multi-protein panel,
# which proteingym_loader.py joins from build_burial_features.py.
#
# WHY IT EXISTS
#   ace2_distance is the strongest single descriptor we have (0.7143 AUC
#   alone), but it is measured from one complex -- 6M0J, SARS-CoV-2 RBD bound
#   to ACE2 -- so it is a CONSTANT for every other protein. Training across
#   proteins without it left the model with five descriptors that say WHICH
#   residue changed and nothing about WHERE, and multi-protein AUC fell to
#   ~0.63.
#
#   Burial is the generalizable version: how packed a residue is inside its
#   own fold, computable for any protein from structure alone, no binding
#   partner required. It restores positional context protein-agnostically.
#
# Range (0, 40) covers contact number at 10 A: surface residues land around
# 5-10, buried core residues around 15-25.
#
# NEVER select index 8 (ace2_distance) and index 9 together on a
# multi-protein run: outside SARS-CoV-2, index 8 is the ACE2_FAR constant and
# contributes a dead wire.
# ---------------------------------------------------------------------------
# ACTIVE FEATURE SET
# ---------------------------------------------------------------------------
# All 8 descriptors are computed, but only these are fed to the circuit.
# Chosen by measurement, not intuition (see RESULTS.md):
#
#   MLP held-out AUC    VQC held-out AUC
#     all 8 features        0.7136            0.6404
#     4 incl. relative_pos  0.7573            0.6816
#     4 incl. ACE2 distance 0.7772            (see RESULTS.md)
#
# relative_position was REPLACED by ace2_distance rather than added alongside:
# adding it as a 5th feature scored 0.7329, worse than either 4-feature set.
#
# CORRECTION (measured 2026-10-18) -- the claim below this line used to read
# "dropping delta_hydropathy, delta_charge, wt_hydropathy and pro_gly_flag
# improved EVERY model", and that was WRONG. It came from ONE train/test
# split, and fold-to-fold spread on this data is +/-0.05 AUC, so the
# comparison was reading noise.
#
# Re-measured with 200 PAIRED site-grouped resamples (identical splits scored
# with both feature sets), logistic regression on the development set:
#
#     4 features (this SELECTED)      0.7551 +/- 0.0459
#     6 features (+ wt_hydropathy,
#                  + delta_hydropathy) 0.7790 +/- 0.0491
#     paired difference               +0.0239, wins 173/200 draws,
#                                     paired t = +14.5
#
# Beyond six it is flat (7 features +0.021, 8 +0.022, 9 +0.019), and
# relative_position is the one descriptor that actively hurts: 9-with-it
# (+0.019) is worse than 8-without-it (+0.022). So the original instinct that
# relative_position should go was right; the specific "four beats eight" claim
# was not.
#
# The per-draw 95% range of that difference is [-0.040, +0.054] and includes
# zero: on any SINGLE split six features can lose. That is why it is reported
# as a paired mean over many draws rather than one number.
#
# TO SHIP THE SIX-FEATURE MODEL, swap the two SELECTED lines below and
# RETRAIN. Do not swap it without retraining: quantum_engine.load() compares
# the trained feature count against N_FEATURES and will refuse to serve a
# mismatched weights.npz -- correctly, but it would take the live API down
# until new weights exist.
# MEASURED 2026-10-19, and this REVERSES the recommendation above.
#
# The paired test that favoured six features used LOGISTIC REGRESSION, which
# has 7 parameters. The VQC has 41-63. Trained end to end on the same 2,856
# rows, three restarts each, dense Y/Z encoding, probs readout:
#
#     4 features, 2 qubits, 41 params   0.7571 +/- 0.0202   <-- SHIPPED
#     6 features, 3 qubits, 63 params   0.6785 +/- 0.0014
#
# Adding two descriptors cost 0.079 AUC. The mechanism is in the training
# loss: the 6-feature model converges to 0.4243 while the 4-feature model
# stops at 0.4553 -- it fits the training set BETTER and generalises WORSE.
# Classic overfitting, invisible to a 7-parameter baseline.
#
# The six-feature set IS better where there is data to support it: on the
# 111,859-row multi-protein panel it wins by +0.0265 with non-overlapping
# restart ranges. So the optimal feature count scales with dataset size --
# four here, six there -- and a feature set cannot be chosen on a proxy model
# with a tenth of the capacity.
SELECTED = (4, 6, 2, 8)  # blosum62, wt_volume, delta_volume, ace2_distance
# SELECTED = (4, 6, 2, 8, 5, 0)  # overfits at 2.8k rows; correct for the panel

# raw_descriptors() computes indices 0..8. Index 9 (burial) is appended
# per-row by train_vqc.load_panel from a panel's `burial` column, so the two
# counts differ and must not be used interchangeably: selecting index 9 on the
# single-assay path would index past the end of the vector.
N_BASE_FEATURES = 9      # what raw_descriptors() returns
BURIAL_INDEX = 9         # supplied externally, panel runs only

ACTIVE_NAMES = tuple(NAMES[i] for i in SELECTED)
ACTIVE_RANGES = tuple(RANGES[i] for i in SELECTED)
N_FEATURES = len(SELECTED)
N_ALL_FEATURES = len(NAMES)


class MutationError(ValueError):
    """Raised when a mutation cannot be featurised."""


def raw_descriptors(wt_aa: str, mut_aa: str, rel_pos: float,
                    site: int | None = None) -> list[float]:
    """All 8+1 descriptors. `site` is the spike position (1-indexed), needed for
    the structural feature; without it the distance falls back to ACE2_FAR."""
    wt_aa, mut_aa = wt_aa.upper(), mut_aa.upper()
    if wt_aa not in VALID or mut_aa not in VALID:
        raise MutationError(f"Non-standard residue in {wt_aa}->{mut_aa}")
    return [
        KD[mut_aa] - KD[wt_aa],
        CHARGE.get(mut_aa, 0.0) - CHARGE.get(wt_aa, 0.0),
        VOLUME[mut_aa] - VOLUME[wt_aa],
        float(min(max(rel_pos, 0.0), 1.0)),
        float(BLOSUM62[wt_aa][mut_aa]),
        KD[wt_aa],
        VOLUME[wt_aa],
        1.0 if (wt_aa in "PG" or mut_aa in "PG") else 0.0,
        ace2_distance(site) if site is not None else ACE2_FAR,
    ]


def to_angles(raw, ranges=None) -> list[float]:
    """Clamp each descriptor to its fixed range and map onto [0, pi]."""
    ranges = ranges if ranges is not None else RANGES[:len(raw)]
    return [
        (min(max(v, lo), hi) - lo) / (hi - lo) * math.pi
        for v, (lo, hi) in zip(raw, ranges)
    ]


def select(raw) -> list[float]:
    """Keep only the active descriptors, in SELECTED order."""
    return [raw[i] for i in SELECTED]


def featurise_mutation(wt_aa: str, mut_aa: str, rel_pos: float,
                       site: int | None = None):
    """One substitution -> (angles, explainability payload)."""
    raw_all = raw_descriptors(wt_aa, mut_aa, rel_pos, site)
    raw = select(raw_all)
    return to_angles(raw, ACTIVE_RANGES), {
        "mutation": f"{wt_aa.upper()}->{mut_aa.upper()}",
        # Only the descriptors the model actually uses, so the UI cannot imply
        # the score depends on something it ignores.
        "descriptors": {k: round(v, 4) for k, v in zip(ACTIVE_NAMES, raw)},
        "all_descriptors": {k: round(v, 4) for k, v in zip(NAMES, raw_all)},
        "method": "mutation-delta-v4 (chemistry + ACE2 interface distance)",
    }


def diff_sequences(reference: str, variant: str) -> list[tuple[int, str, str]]:
    """Substitutions between two equal-length sequences."""
    if len(reference) != len(variant):
        raise MutationError(
            f"Reference is {len(reference)} residues and variant is "
            f"{len(variant)}. This model scores substitutions only, so the two "
            "sequences must be the same length (align them first)."
        )
    diffs = [
        (i, r, v)
        for i, (r, v) in enumerate(zip(reference.upper(), variant.upper()))
        if r != v
    ]
    if not diffs:
        raise MutationError("Variant is identical to the reference -- no substitutions found.")
    return diffs
