"""
Surveillance sentinel — the real pipeline, end to end.

WHAT IT DOES
------------
1. Asks NCBI for recently deposited SARS-CoV-2 spike protein sequences.
2. Compares each against the Wuhan-Hu-1 reference to find substitutions.
3. Keeps the ones inside the receptor-binding domain (spike sites 331-531),
   which is the only region the model is trained on.
4. Scores every RBD substitution with the trained VQC.
5. Ranks the deposited sequences by their highest-scoring mutation and caches
   the result.

That is the actual product: a new sequence appears -> which of its mutations
deserve a closer look.

WHY IT IS CACHED, NOT LIVE
--------------------------
NCBI is rate-limited and sometimes slow, and a free-tier dyno sleeps. A live
fetch on page load is a demo that hangs in front of a judge. So the cache is
built by running this file, committed to the repo, and served instantly. The
fetch timestamp is shown in the UI so nobody mistakes cached data for live data.

Refresh it with:
    python sentinel.py

HONEST LIMITS (all surfaced in the output)
------------------------------------------
- We LOCALLY ALIGN the reference RBD against each deposited sequence
  (Smith-Waterman, BLOSUM62) instead of requiring identical lengths. Deposited
  spikes are frequently partial sequences or carry indels elsewhere in the
  protein; demanding an exact length match rejected essentially everything.
- Positions that align to a gap are insertions/deletions. This is a
  substitution-only model, so those are counted and reported, never scored.
- Mutations outside sites 331-531 are counted but not scored, because the model
  has no training signal there.
- The model was trained on SINGLE mutants, so a sequence carrying several RBD
  mutations is scored per-mutation. Epistasis is not modelled.
- A high score means "this substitution resembles ones that preserved ACE2
  binding in the Starr et al. assay". It is NOT a prediction that the variant
  will spread.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import httpx
from Bio import Align
from Bio.Align import substitution_matrices

import mutation_features as mutfeat

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.getenv("SENTINEL_CACHE_PATH", os.path.join(HERE, "sentinel_cache.json"))
PANEL_PATH = os.path.join(HERE, "reference_panel.json")

REFERENCE_NAME = "SARS-CoV-2 spike (Wuhan-Hu-1 reference)"
RBD_START, RBD_END = 331, 531          # inclusive, 1-indexed spike numbering
RBD_LENGTH = RBD_END - RBD_START + 1
TIMEOUT = 30.0


# ---------------------------------------------------------------- cache io

def load_cache() -> dict:
    try:
        with open(CACHE_PATH) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _json_default(o):
    """Last-resort coercion for numpy scalars so a long NCBI run is never lost
    to a serialisation error at the final step."""
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _save_cache(payload: dict) -> None:
    tmp = CACHE_PATH + ".tmp"
    try:
        with open(tmp, "w") as fh:
            json.dump(payload, fh, indent=2, default=_json_default)
        os.replace(tmp, CACHE_PATH)   # atomic; a crash mid-write cannot corrupt it
    except OSError as exc:
        print(f"[sentinel] could not write cache: {exc}")


def _reference_sequence() -> str | None:
    try:
        with open(PANEL_PATH) as fh:
            panel = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    entry = panel.get(REFERENCE_NAME)
    return entry.get("sequence") if entry else None


# ---------------------------------------------------------------- ncbi

def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": "q-vira/2.3"})


def _params(extra: dict) -> dict:
    p = dict(extra)
    p["tool"] = "q-vira"
    if os.getenv("NCBI_API_KEY"):
        p["api_key"] = os.getenv("NCBI_API_KEY")
    if os.getenv("NCBI_EMAIL"):
        p["email"] = os.getenv("NCBI_EMAIL")
    return p


def search_recent_spikes(limit: int = 40) -> list[str]:
    """UIDs of recently deposited SARS-CoV-2 spike proteins, newest first."""
    term = "txid2697049[Organism] AND surface glycoprotein[Protein Name]"
    try:
        with _client() as client:
            resp = client.get(ESEARCH, params=_params({
                "db": "protein", "term": term, "retmax": limit,
                "retmode": "json", "sort": "most_recent",
            }))
            resp.raise_for_status()
            return resp.json().get("esearchresult", {}).get("idlist", [])
    except Exception as exc:
        print(f"[sentinel] search failed: {type(exc).__name__}: {exc}")
        return []


def fetch_fastas(uids: list[str]) -> list[str]:
    """Fetch many records in ONE request rather than one call per accession."""
    if not uids:
        return []
    try:
        with _client() as client:
            resp = client.get(EFETCH, params=_params({
                "db": "protein", "id": ",".join(uids),
                "rettype": "fasta", "retmode": "text",
            }))
            resp.raise_for_status()
        blocks = [b.strip() for b in resp.text.split("\n>") if b.strip()]
        return [b if b.startswith(">") else ">" + b for b in blocks]
    except Exception as exc:
        print(f"[sentinel] fetch failed: {type(exc).__name__}: {exc}")
        return []


# ---------------------------------------------------------------- analysis

def _clean(body: str) -> str:
    return "".join(c for c in body.upper() if c in mutfeat.VALID)


_ALIGNER = None


def _aligner() -> Align.PairwiseAligner:
    """Local (Smith-Waterman) aligner with standard protein gap penalties."""
    global _ALIGNER
    if _ALIGNER is None:
        a = Align.PairwiseAligner()
        a.mode = "local"
        a.substitution_matrix = substitution_matrices.load("BLOSUM62")
        a.open_gap_score = -11
        a.extend_gap_score = -1
        _ALIGNER = a
    return _ALIGNER


def find_rbd_substitutions(reference: str, query: str):
    """Align the reference RBD onto a deposited sequence.

    Returns (substitutions, stats). Each substitution is (spike_position,
    wild_type, mutant) in SARS-CoV-2 spike numbering.

    Why alignment rather than a length check: deposited spike records are often
    partial, and indels elsewhere in the protein shift every downstream index.
    Local alignment finds the RBD wherever it sits and tolerates both.
    """
    rbd_ref = reference[RBD_START - 1:RBD_END]
    try:
        alignments = _aligner().align(rbd_ref, query)
        aln = alignments[0]
    except Exception as exc:
        return None, {"error": f"alignment failed: {type(exc).__name__}: {exc}"}

    ref_blocks, qry_blocks = aln.aligned
    subs, matched, gapped = [], 0, 0
    for (rs, re_), (qs, qe) in zip(ref_blocks, qry_blocks):
        for off in range(re_ - rs):
            r_idx = rs + off          # index within the RBD window
            wt = rbd_ref[r_idx]
            mut = query[qs + off]
            matched += 1
            if wt != mut and mut in mutfeat.VALID:
                # int() is required: aln.aligned yields numpy integers, which
                # json.dump cannot serialise ("Object of type int32 is not JSON
                # serializable"). Cast at the boundary, not at save time.
                subs.append((int(RBD_START + r_idx), str(wt), str(mut)))

    gapped = len(rbd_ref) - matched
    identity = matched / len(rbd_ref) if rbd_ref else 0.0
    return subs, {
        "rbd_positions_aligned": int(matched),
        "rbd_positions_unaligned": int(gapped),
        "rbd_coverage": round(float(identity), 4),
        "alignment_score": float(aln.score),
    }


# Below this coverage the record is not really an RBD-containing spike.
MIN_RBD_COVERAGE = 0.80


def analyse_record(fasta: str, reference: str, engine) -> dict | None:
    """One FASTA record -> scored RBD substitutions, or a 'skipped' marker."""
    lines = fasta.splitlines()
    if not lines:
        return None
    header = lines[0].lstrip(">").strip()
    accession = header.split()[0] if header else "unknown"
    seq = _clean("".join(lines[1:]))
    if len(seq) < 50:
        return {"accession": accession, "description": header, "skipped": True,
                "skip_reason": f"sequence too short ({len(seq)} residues)"}

    subs, stats = find_rbd_substitutions(reference, seq)
    if subs is None:
        return {"accession": accession, "description": header, "skipped": True,
                "skip_reason": stats.get("error", "alignment failed")}

    if stats["rbd_coverage"] < MIN_RBD_COVERAGE:
        return {
            "accession": accession, "description": header, "skipped": True,
            "skip_reason": (
                f"only {stats['rbd_coverage']:.0%} of the receptor-binding domain "
                "is present (partial sequence)"
            ),
            "rbd_coverage": stats["rbd_coverage"],
        }

    scored = []
    for pos, wt, mut in subs:
        rel = (pos - RBD_START) / RBD_LENGTH
        try:
            angles, explain = mutfeat.featurise_mutation(wt, mut, rel, site=pos)
        except mutfeat.MutationError:
            continue
        r = engine.score(angles, with_error_bar=False)
        scored.append({
            "mutation": f"{wt}{pos}{mut}",
            "position": pos,
            "score": round(r["threat_score"], 4),
            "descriptors": explain["descriptors"],
            # False => the site is outside the 6M0J construct, so its distance
            # is the far-field fallback rather than a measurement.
            "has_structure": mutfeat.has_ace2_structure(pos),
        })
    scored.sort(key=lambda s: s["score"], reverse=True)

    return {
        "accession": accession,
        "description": header,
        "skipped": False,
        "sequence_length": len(seq),
        "rbd_substitutions": len(scored),
        "rbd_coverage": stats["rbd_coverage"],
        "rbd_positions_unaligned": stats["rbd_positions_unaligned"],
        "mutations": scored,
        "max_score": scored[0]["score"] if scored else None,
        "driver_mutation": scored[0]["mutation"] if scored else None,
    }


# A sequence this far from Wuhan-Hu-1 is a descendant of a heavily diverged
# lineage (Omicron and later). The model was trained on SINGLE mutants of the
# reference, so scoring 30 co-occurring substitutions independently ignores
# epistasis entirely -- and epistasis in the RBD is large and well documented.
# We still show the scores, but we flag the sequence rather than implying the
# number means as much as it does for a single mutation.
HIGH_DIVERGENCE_THRESHOLD = 5


def _signature(rec: dict) -> str:
    """Identical mutation sets collapse to one row."""
    return ",".join(sorted(m["mutation"] for m in rec.get("mutations", [])))


def deduplicate(records: list[dict]) -> list[dict]:
    """Collapse records with an identical RBD mutation set.

    NCBI deposits arrive in batches: 40 sequences from one submission can carry
    exactly the same RBD substitutions. Listing them 40 times is noise, and it
    makes the feed look like it found 40 findings when it found one.
    """
    groups: dict[str, dict] = {}
    for rec in records:
        sig = _signature(rec)
        if sig in groups:
            g = groups[sig]
            g["identical_count"] += 1
            if len(g["identical_accessions"]) < 8:
                g["identical_accessions"].append(rec["accession"])
        else:
            rec = dict(rec)
            rec["identical_count"] = 1
            rec["identical_accessions"] = [rec["accession"]]
            groups[sig] = rec
    return list(groups.values())


def build_payload(records: list[dict], skipped: list[dict], reference: str,
                  n_requested: int) -> dict:
    n_before = len(records)
    records = deduplicate(records)

    # Every circulating lineage shares the same ~30 Omicron-era RBD mutations,
    # so ranking by the single highest-scoring mutation ties everything at the
    # same value and tells you nothing. What distinguishes one deposit from
    # another is the mutations it does NOT share with the rest of the batch.
    scored_recs = [r for r in records if r.get("mutations")]
    if scored_recs:
        shared = set.intersection(*[
            {m["mutation"] for m in r["mutations"]} for r in scored_recs
        ])
    else:
        shared = set()

    for r in records:
        muts = r.get("mutations", [])
        scores = [m["score"] for m in muts]
        r["high_divergence"] = r["rbd_substitutions"] >= HIGH_DIVERGENCE_THRESHOLD
        r["mean_score"] = round(sum(scores) / len(scores), 4) if scores else None
        r["n_high_scoring"] = sum(1 for x in scores if x >= 0.8)
        distinguishing = [m for m in muts if m["mutation"] not in shared]
        r["distinguishing_mutations"] = distinguishing
        r["n_distinguishing"] = len(distinguishing)
        r["n_without_structure"] = sum(1 for m in muts if not m["has_structure"])

        # Rank on sites that were actually resolved in 6M0J. Sites outside the
        # construct receive the far-field fallback distance, which the model
        # scores highly -- ranking on those would promote missing data to the
        # top of a triage list. They are still shown, just not used to rank.
        ranked = [m for m in distinguishing if m["has_structure"]] or []
        r["top_distinguishing"] = (
            max(ranked, key=lambda m: m["score"])["mutation"] if ranked else None
        )
        r["top_distinguishing_score"] = (
            max(m["score"] for m in ranked) if ranked else None
        )
        r["ranked_on_resolved_sites_only"] = True

    # Rank by what is actually different about each deposit, then by how many of
    # its mutations score highly. Records with nothing distinctive sort last.
    records.sort(
        key=lambda r: (
            r["top_distinguishing_score"] is not None,
            r["top_distinguishing_score"] or 0,
            r["n_high_scoring"],
        ),
        reverse=True,
    )
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "NCBI protein, SARS-CoV-2 (txid2697049) surface glycoprotein",
        "reference": REFERENCE_NAME,
        "reference_length": len(reference),
        "rbd_window": f"{RBD_START}-{RBD_END}",
        "n_requested": n_requested,
        "n_analysed": n_before,
        "n_distinct_variants": len(records),
        "shared_mutations": sorted(shared),
        "n_shared_mutations": len(shared),
        "n_skipped": len(skipped),
        "records": records,
        "skipped_records": skipped[:20],
        "caveats": [
            "Cached, not live. The timestamp is when NCBI was last queried.",
            "The reference RBD is located in each record by local alignment "
            "(Smith-Waterman, BLOSUM62), so partial sequences and indels "
            "elsewhere in the spike are handled rather than rejected.",
            "Records covering less than 80% of the RBD are skipped and counted, "
            "not silently dropped.",
            "Only substitutions inside spike sites 331-531 are scored; the "
            "model has no training signal elsewhere.",
            "Trained on single mutants, so each substitution is scored "
            "independently. Epistasis is not modelled.",
            "A high score means the substitution resembles ones that preserved "
            "ACE2 binding in the Starr et al. assay. It is NOT a prediction "
            "that the variant will spread.",
            "Sequences carrying many co-occurring RBD substitutions are flagged "
            "as high-divergence. The model was trained on SINGLE mutants of "
            "Wuhan-Hu-1, so scoring 30 simultaneous substitutions independently "
            "ignores epistasis, which is large in the RBD. Treat those scores as "
            "far weaker evidence than a single-substitution score.",
            "Records with an identical RBD mutation set are collapsed into one "
            "row with a count, because NCBI deposits arrive in batches and "
            "listing them separately would overstate how much was found.",
            "Ranking uses only sites resolved in the crystal structure 6M0J "
            "(RBD 333-526). Sites outside it (331-332, 527-531) get a far-field "
            "fallback distance that the model scores highly, so ranking on them "
            "would promote MISSING DATA to the top of a triage list. Those "
            "mutations are still displayed and flagged.",
            "Ranking is by the highest-scoring DISTINGUISHING mutation — one not "
            "shared by every deposit in the batch. Current lineages share ~30 "
            "Omicron-era RBD mutations, so ranking by the single best mutation "
            "ties every record at the same value and conveys nothing.",
        ],
    }


def refresh(limit: int = 40) -> dict:
    """Fetch, analyse, score and cache. Returns the new cache payload."""
    from quantum_engine import engine

    if not engine.is_trained:
        raise RuntimeError("Model is untrained — run train_vqc.py first.")

    reference = _reference_sequence()
    if not reference:
        raise RuntimeError(
            f"'{REFERENCE_NAME}' not found in reference_panel.json. "
            "Run build_panel.py first."
        )

    uids = search_recent_spikes(limit)
    if not uids:
        raise RuntimeError("NCBI returned no records (rate limit or no network).")

    print(f"[sentinel] fetching {len(uids)} records…")
    fastas = fetch_fastas(uids)
    if not fastas:
        raise RuntimeError("NCBI returned no sequence data.")

    analysed, skipped = [], []
    for fasta in fastas:
        rec = analyse_record(fasta, reference, engine)
        if rec is None:
            continue
        (skipped if rec.get("skipped") else analysed).append(rec)

    payload = build_payload(analysed, skipped, reference, len(uids))
    _save_cache(payload)
    print(f"[sentinel] analysed {len(analysed)}, skipped {len(skipped)} -> {CACHE_PATH}")
    return payload


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    try:
        out = refresh()
    except RuntimeError as exc:
        sys.exit(f"ERROR: {exc}")
    print(f"[sentinel] {out['n_analysed']} records -> "
          f"{out['n_distinct_variants']} distinct RBD mutation sets")
    top = [r for r in out["records"] if r["max_score"] is not None][:10]
    if not top:
        print("\nNo RBD substitutions in this batch. That is a normal result, "
              "not a failure — most deposited spikes match the reference there.")
    print(f"[sentinel] {out['n_shared_mutations']} RBD mutations are shared by "
          f"EVERY deposit; ranking uses the rest\n")
    for r in top:
        td = r["top_distinguishing"] or "-- nothing distinctive --"
        tds = r["top_distinguishing_score"]
        print(f"  {tds if tds is not None else 0:.3f}  {r['accession']:16s} "
              f"{td:12s} ({r['n_distinguishing']} distinguishing / "
              f"{r['rbd_substitutions']} RBD, x{r['identical_count']})")
