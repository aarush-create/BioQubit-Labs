"""
Nearest-reference lookup.

WHAT CHANGED AND WHY
--------------------
The original code did `100 - distance * 40` and printed it as
"database_confidence_percent", next to a label saying "NCBI Database Match".
That reads as a taxonomic identification. It is not one, and it cannot be:
you cannot identify a virus from 4 physicochemical numbers. In testing, a
SARS-CoV-2 spike fragment was reported as "Zika Virus (45.5% match)".

This module keeps the useful part -- showing which reference sequence sits
closest in descriptor space -- and drops the part that was misleading. It
reports a distance and an explicit disclaimer, and refuses to name a match
at all when the nearest neighbour is far away.

If you want real taxonomic identification, that is BLAST or minimap2 against
a sequence database, not a 4-vector. Put it on the roadmap slide.
"""

from __future__ import annotations

import json
import math
import os

PANEL_PATH = os.path.join(os.path.dirname(__file__), "reference_panel.json")

# Beyond this descriptor-space distance we decline to name a nearest entry.
# pi is the full range of a single angle, so this is a deliberately loose
# "nothing in the panel is remotely similar" guard.
MAX_MEANINGFUL_DISTANCE = 2.0


def _load() -> dict:
    try:
        with open(PANEL_PATH) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def panel_size() -> int:
    return len(_load())


def list_references() -> list[dict]:
    """Panel entries that carry a usable sequence for variant scoring."""
    return [
        {"name": k, "length": len(v["sequence"]), "accession": v.get("ncbi_accession")}
        for k, v in _load().items()
        if v.get("sequence")
    ]


def get_reference(name: str) -> str | None:
    """Sequence for a panel entry, matched case-insensitively."""
    panel = _load()
    if name in panel:
        return panel[name].get("sequence")
    low = name.lower()
    for k, v in panel.items():
        if k.lower() == low or low in k.lower():
            return v.get("sequence")
    return None


def nearest_reference(angles) -> dict:
    """Closest entry in the reference panel, or an explicit 'no match'."""
    panel = _load()
    if not panel:
        return {
            "name": None,
            "note": "Reference panel is empty. Run build_panel.py to populate it.",
        }

    best_name, best_dist, best_rec = None, math.inf, {}
    for name, rec in panel.items():
        vec = rec.get("vector")
        if not vec or len(vec) != len(angles):
            continue
        d = math.dist(angles, vec)
        if d < best_dist:
            best_name, best_dist, best_rec = name, d, rec

    if best_name is None:
        return {"name": None, "note": "No comparable entries in the panel."}

    if best_dist > MAX_MEANINGFUL_DISTANCE:
        return {
            "name": None,
            "distance": round(best_dist, 3),
            "note": (
                "No reference within the similarity threshold. Treat this as "
                "an uncharacterised profile."
            ),
        }

    return {
        "name": best_name,
        "distance": round(best_dist, 3),
        "ncbi_accession": best_rec.get("ncbi_accession"),
        "pdb_id": best_rec.get("pdb_id"),
        "transmission": best_rec.get("transmission"),
        "source": best_rec.get("source", "unknown"),
        "note": (
            "Nearest neighbour in 4-D physicochemical descriptor space. This "
            "is a similarity cue, NOT a taxonomic identification -- use BLAST "
            "for that."
        ),
    }
