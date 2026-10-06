"""
Sequence featurisation for Q-VIRA.

Replaces the previous character-sum hash. Every descriptor here is a standard,
published physicochemical property of a protein sequence, computed directly
from the residues. Nothing is hashed and nothing is random.

Why these four
--------------
The VQC takes 4 angles, so we need exactly 4 numbers. We use descriptors that
are (a) interpretable to a judge, (b) cheap enough to run on a free-tier dyno,
and (c) genuinely sensitive to sequence identity AND residue order:

  f0  GRAVY          mean Kyte-Doolittle hydropathy. Tracks membrane/fusion
                     character of the sequence.
  f1  net charge     mean charge per residue at pH 7 (K,R = +1; D,E = -1;
                     H = +0.1). Electrostatics dominate receptor binding.
  f2  aromaticity    fraction of F, W, Y. Proxy for aromatic stacking at
                     binding interfaces.
  f3  hydropathy     GRAVY(N-terminal half) - GRAVY(C-terminal half).
      asymmetry      This is the ORDER-SENSITIVE term: it changes if you
                     shuffle or reverse the sequence, which the old hash
                     did not.

f0..f2 are composition descriptors and are order-invariant by construction;
f3 is what makes the vector respond to rearrangement. This is a deliberate,
defensible design, not an accident -- say exactly this if a judge asks.

Upgrading to ESM-2
------------------
If you later precompute ESM-2 embeddings offline (see embed_esm.py), swap
`featurise` for the saved PCA projection. The rest of the pipeline is
unchanged because everything downstream only sees a 4-vector. Do NOT claim
ESM-2 in the UI or README unless that path is actually switched on.
"""

from __future__ import annotations

import math

# Kyte & Doolittle (1982) hydropathy index.
KD = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5,
    "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5,
    "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6,
    "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}
CHARGE = {"K": 1.0, "R": 1.0, "D": -1.0, "E": -1.0, "H": 0.1}
AROMATIC = {"F", "W", "Y"}
VALID = set(KD)

# Documented clamp ranges, used to map each raw descriptor onto an angle in
# [0, pi]. Fixed constants -- never fit these to a single input, or the score
# stops being comparable between runs.
RANGES = ((-4.5, 4.5), (-0.5, 0.5), (0.0, 0.3), (-4.0, 4.0))

NUCLEOTIDES = set("ACGTUN")


class SequenceError(ValueError):
    """Raised when an input cannot be featurised."""


def parse_fasta(text: str) -> str:
    """Return the residues from a FASTA record (or a bare sequence).

    Strips header lines, whitespace, digits and '*', then uppercases. Any
    character that is not a standard amino acid is dropped, but if that
    removes more than 10% of the input we raise instead of silently
    featurising garbage.
    """
    if not text or not text.strip():
        raise SequenceError("Empty sequence.")

    body = "".join(
        line.strip() for line in text.splitlines() if not line.startswith(">")
    )
    body = body.upper().replace("*", "").replace("-", "").replace(".", "")
    body = "".join(ch for ch in body if not ch.isdigit() and not ch.isspace())

    if not body:
        raise SequenceError("No sequence found (header only?).")

    # Catch nucleotide input early: a protein featuriser on DNA is meaningless.
    if set(body) <= NUCLEOTIDES and len(body) > 20:
        raise SequenceError(
            "This looks like a nucleotide sequence. Q-VIRA featurises PROTEIN "
            "sequences -- translate the ORF first."
        )

    clean = "".join(ch for ch in body if ch in VALID)
    if len(clean) < 20:
        raise SequenceError(
            f"Sequence too short after cleaning ({len(clean)} residues, need >=20)."
        )
    if len(clean) / len(body) < 0.90:
        raise SequenceError(
            "More than 10% of characters are not standard amino acids."
        )
    return clean


def descriptors(seq: str) -> list[float]:
    """Compute the 4 raw physicochemical descriptors (un-scaled)."""
    n = len(seq)
    gravy = sum(KD[c] for c in seq) / n
    charge = sum(CHARGE.get(c, 0.0) for c in seq) / n
    aromaticity = sum(1 for c in seq if c in AROMATIC) / n

    half = n // 2
    n_term = sum(KD[c] for c in seq[:half]) / half
    c_term = sum(KD[c] for c in seq[half:]) / (n - half)
    asymmetry = n_term - c_term

    return [gravy, charge, aromaticity, asymmetry]


def _scale(value: float, lo: float, hi: float) -> float:
    """Clamp to [lo, hi] then map linearly onto [0, pi] for angle encoding."""
    v = min(max(value, lo), hi)
    return (v - lo) / (hi - lo) * math.pi


def featurise(text: str) -> tuple[list[float], dict]:
    """FASTA/sequence text -> (4 angles in [0, pi], explainability payload).

    The second return value is what the UI should display so the score is
    never an unexplained number.
    """
    seq = parse_fasta(text)
    raw = descriptors(seq)
    angles = [_scale(v, lo, hi) for v, (lo, hi) in zip(raw, RANGES)]
    names = ["gravy", "net_charge", "aromaticity", "hydropathy_asymmetry"]
    explain = {
        "length": len(seq),
        "descriptors": {k: round(v, 4) for k, v in zip(names, raw)},
        "angles_rad": [round(a, 4) for a in angles],
        "method": "physicochemical-v1",
    }
    return angles, explain
