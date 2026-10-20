"""
proteingym_loader.py -- turn ProteinGym assays into one training table.

WHAT THIS GIVES YOU
-------------------
217 assays across 186 proteins, 696,311 single mutants. 31 of those assays are
viral, covering 21 organisms: Zika, HIV-1, four influenza strains, Dengue-2,
Hepatitis C, Coxsackievirus B3, AAV-2, SARS-CoV-2, and several phages --
178,050 single mutants on viruses alone, against the 3,802 we train on today.

Why this expands the dataset in a way the SARS-CoV-2 panel could not: our
descriptors are functions of (site, wildtype, mutant) WITHIN a protein, so one
protein caps out at seq_len x 19 possible feature vectors no matter how many
genetic backgrounds we add. A different protein has different residues at
different positions, so every new protein contributes genuinely new feature
vectors.

SETUP
-----
    curl -O https://marks.hms.harvard.edu/proteingym/ProteinGym_v1.3/DMS_ProteinGym_substitutions.zip
    unzip DMS_ProteinGym_substitutions.zip -d proteingym_data

You also need the assay index, which ships in the ProteinGym repo:
    git clone --depth 1 https://github.com/OATML-Markslab/ProteinGym
    -> ProteinGym/reference_files/DMS_substitutions.csv

VERIFIED SCHEMA (checked against ProteinGym v1.3 repo code, 2026-10-18)
----------------------------------------------------------------------
Per-assay csv columns used here:
    mutant          substitution(s). Single: "I291A". MULTIPLE mutants are
                    COLON-separated ("I291A:K294R") -- their own benchmark code
                    computes mutation depth as mutant.split(":"), and we keep
                    depth-1 rows only.
    DMS_score       continuous fitness/binding score
    DMS_score_bin   binary label, 1 = mutation has an effect, 0 = none.
                    This is ProteinGym's own binarization at the cutoff
                    recorded per assay in the index, so no threshold is chosen
                    here.

LABEL POLARITY -- read this before trusting any AUC
---------------------------------------------------
In our SARS-CoV-2 pipeline, label 1 means "RETAINS binding" (bind_avg >= -1.0).
In ProteinGym, DMS_score_bin = 1 means the mutation "has an EFFECT", i.e. it is
the DISRUPTIVE class. Those are opposite conventions. Left unflipped, every AUC
would come out mirrored around 0.5 and a genuinely good model would look
terrible.

--polarity controls this:
    retain   (default) label = 1 - DMS_score_bin, so 1 means tolerated/retained,
             matching the existing pipeline and the existing weights.
    effect   label = DMS_score_bin, ProteinGym's own convention.

The script prints both rates so the choice is visible, not buried.

Usage
-----
    # all 31 viral assays
    python proteingym_loader.py --data-dir proteingym_data \
        --index ProteinGym/reference_files/DMS_substitutions.csv \
        --taxon Virus --out data/pg_virus.csv

    # just the big viral ones, capped for a first run
    python proteingym_loader.py --data-dir proteingym_data \
        --index ProteinGym/reference_files/DMS_substitutions.csv \
        --taxon Virus --min-mutants 2000 --max-assays 12 \
        --out data/pg_virus12.csv
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

import numpy as np
import pandas as pd

# wildtype residue, 1-based position, mutant residue
MUT_RE = re.compile(r"^([A-Z])(\d+)([A-Z])$")
STANDARD_AA = set("ACDEFGHIKLMNPQRSTVWY")
OUT_COLS = ["protein", "taxon", "organism", "site_SARS2", "wildtype",
            "mutant", "mutation", "dms_score", "label"]
# "burial" is appended by the --burial join when requested.


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_mutant(s: str):
    """'I291A' -> ('I', 291, 'A'). Returns None if not a single standard
    substitution. Multiple mutants are colon-separated and rejected here."""
    if not isinstance(s, str) or ":" in s:
        return None
    m = MUT_RE.match(s.strip())
    if not m:
        return None
    wt, pos, mut = m.group(1), int(m.group(2)), m.group(3)
    if wt not in STANDARD_AA or mut not in STANDARD_AA or wt == mut:
        return None
    return wt, pos, mut


def load_assay(path: str, polarity: str) -> pd.DataFrame | None:
    try:
        d = pd.read_csv(path)
    except Exception as e:                       # noqa: BLE001
        print(f"    skipped (unreadable: {e})")
        return None

    if "mutant" not in d.columns or "DMS_score_bin" not in d.columns:
        print(f"    skipped (missing mutant/DMS_score_bin; has "
              f"{sorted(d.columns)[:6]}...)")
        return None

    n0 = len(d)
    parsed = d["mutant"].map(parse_mutant)
    keep = parsed.notna()
    d = d[keep].copy()
    p = parsed[keep]
    d["wildtype"] = [t[0] for t in p]
    d["site_SARS2"] = [t[1] for t in p]
    d["mutant_aa"] = [t[2] for t in p]

    d = d.dropna(subset=["DMS_score_bin"])
    bin_raw = d["DMS_score_bin"].astype(int)
    d["label"] = (1 - bin_raw) if polarity == "retain" else bin_raw
    d["dms_score"] = pd.to_numeric(d.get("DMS_score"), errors="coerce")

    print(f"    kept {len(d)} of {n0} rows "
          f"(dropped {n0 - len(d)}: multi-mutant, non-standard or no label) | "
          f"effect-rate {bin_raw.mean():.3f} -> label-rate {d['label'].mean():.3f}")
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True,
                    help="unzipped DMS_ProteinGym_substitutions directory")
    ap.add_argument("--index", required=True,
                    help="ProteinGym reference_files/DMS_substitutions.csv")
    ap.add_argument("--taxon", default=None,
                    help="Virus | Human | Prokaryote | Eukaryote (default: all)")
    ap.add_argument("--selection-type", default=None,
                    help="Growth | Binding | FACS | 'cDNA display proteolysis'. "
                         "STRONGLY RECOMMENDED: assays measure different "
                         "phenotypes, and pooling them asks one binary label to "
                         "mean 'virus replicates' AND 'protein resists "
                         "proteolysis' AND 'binds receptor' at once. 'Growth' "
                         "is the largest coherent viral set: 19 assays, "
                         "157k mutants, 13 organisms, all replication fitness.")
    ap.add_argument("--coarse-selection-type", default=None,
                    help="OrganismalFitness | Stability | Activity | Binding | "
                         "Expression (coarser grouping of the above)")
    ap.add_argument("--assays", default=None,
                    help="comma-separated DMS_id list, overrides --taxon")
    ap.add_argument("--min-mutants", type=int, default=0)
    ap.add_argument("--max-assays", type=int, default=None)
    ap.add_argument("--burial", default=None,
                    help="burial.json from build_burial_features.py. Adds a "
                         "per-site burial column (contact number), the "
                         "protein-agnostic replacement for ace2_distance. The "
                         "join is VERIFIED against the wildtype residue, "
                         "because AF2 numbering and DMS numbering can differ "
                         "and a silent offset would attach the wrong residue's "
                         "burial to every row.")
    ap.add_argument("--min-wt-match", type=float, default=0.90,
                    help="drop a protein whose structure residues disagree "
                         "with the DMS wildtype more often than this allows. "
                         "A low match means the structure is numbered "
                         "differently from the assay (often an AF2 model of a "
                         "fragment against full-polyprotein positions), so the "
                         "burial values are effectively random. Those rows "
                         "look fine and train fine and are pure noise, which "
                         "is why this gate is per-protein and on by default.")
    ap.add_argument("--min-coverage", type=float, default=0.80,
                    help="drop a protein with fewer than this fraction of its "
                         "sites present in the structure")
    ap.add_argument("--burial-radius", default="cn10",
                    choices=["cn8", "cn10", "cn13"],
                    help="which contact radius to use as the feature")
    ap.add_argument("--polarity", choices=["retain", "effect"],
                    default="retain",
                    help="retain = 1 means tolerated (matches our pipeline); "
                         "effect = ProteinGym's own convention")
    ap.add_argument("--out", default="data/proteingym.csv")
    args = ap.parse_args()

    if not os.path.isdir(args.data_dir):
        die(f"--data-dir {args.data_dir} is not a directory")
    if not os.path.exists(args.index):
        die(f"--index {args.index} not found")

    idx = pd.read_csv(args.index)
    need = {"DMS_id", "DMS_filename", "taxon", "source_organism",
            "DMS_number_single_mutants"}
    # selection_type is optional in older index versions; checked on use.
    missing = need - set(idx.columns)
    if missing:
        die(f"index missing columns {sorted(missing)}")

    sel = idx.copy()
    if args.assays:
        wanted = {a.strip() for a in args.assays.split(",")}
        sel = sel[sel["DMS_id"].isin(wanted)]
        unknown = wanted - set(sel["DMS_id"])
        if unknown:
            print(f"WARNING: unknown DMS_id(s): {sorted(unknown)}")
    elif args.taxon:
        sel = sel[sel["taxon"].astype(str).str.lower() == args.taxon.lower()]
    if args.selection_type:
        if "selection_type" not in sel.columns:
            die("index has no selection_type column")
        sel = sel[sel["selection_type"].astype(str).str.lower()
                  == args.selection_type.lower()]
    if args.coarse_selection_type:
        if "coarse_selection_type" not in sel.columns:
            die("index has no coarse_selection_type column")
        sel = sel[sel["coarse_selection_type"].astype(str).str.lower()
                  == args.coarse_selection_type.lower()]
    sel = sel[sel["DMS_number_single_mutants"] >= args.min_mutants]
    sel = sel.sort_values("DMS_number_single_mutants", ascending=False)
    if args.max_assays:
        sel = sel.head(args.max_assays)
    if sel.empty:
        die("no assays matched. Check --taxon / --assays / --min-mutants.")

    print(f"selected {len(sel)} assays "
          f"({int(sel['DMS_number_single_mutants'].sum())} single mutants "
          f"claimed by the index), polarity={args.polarity}\n")

    frames, skipped = [], []
    for r in sel.itertuples(index=False):
        print(f"  {r.DMS_id}  [{r.taxon}] {str(r.source_organism)[:48]}")
        # The index gives the filename; fall back to a recursive search because
        # the zip's internal layout has changed between releases.
        path = os.path.join(args.data_dir, str(r.DMS_filename))
        if not os.path.exists(path):
            hits = []
            for root, _dirs, files in os.walk(args.data_dir):
                if str(r.DMS_filename) in files:
                    hits.append(os.path.join(root, str(r.DMS_filename)))
                    break
            if not hits:
                print("    skipped (file not found in --data-dir)")
                skipped.append(r.DMS_id)
                continue
            path = hits[0]

        d = load_assay(path, args.polarity)
        if d is None or d.empty:
            skipped.append(r.DMS_id)
            continue
        out = pd.DataFrame({
            "protein": r.DMS_id,
            "taxon": r.taxon,
            "organism": r.source_organism,
            "site_SARS2": d["site_SARS2"].astype(int),
            "wildtype": d["wildtype"],
            "mutant": d["mutant_aa"],
            "dms_score": d["dms_score"],
            "label": d["label"].astype(int),
        })
        out["mutation"] = (out["wildtype"] + out["site_SARS2"].astype(str)
                           + out["mutant"])
        frames.append(out[OUT_COLS])

    if not frames:
        die("every selected assay failed to load. Check --data-dir layout.")

    df = pd.concat(frames, ignore_index=True)

    if args.burial:
        with open(args.burial) as fh:
            bur = json.load(fh)
        key = args.burial_radius
        vals, aa_struct = [], []
        for r in df.itertuples(index=False):
            rec = bur.get(r.protein, {}).get(str(int(r.site_SARS2)))
            if rec is None:
                vals.append(np.nan); aa_struct.append(None)
            else:
                vals.append(float(rec[key])); aa_struct.append(rec.get("aa"))
        df["burial"] = vals
        df["_aa_struct"] = aa_struct

        print(f"\n--- burial join ({key}) ------------------------------------")
        print(f"{'protein':<36}{'covered':>9}{'wt match':>10}")
        bad = []
        for prot, sub in df.groupby("protein", sort=False):
            cov = float(sub["burial"].notna().mean())
            have = sub.dropna(subset=["_aa_struct"])
            match = (float((have["wildtype"] == have["_aa_struct"]).mean())
                     if len(have) else float("nan"))
            print(f"{prot[:35]:<36}{cov:>9.3f}{match:>10.3f}")
            if cov < args.min_coverage or (match == match
                                           and match < args.min_wt_match):
                bad.append(prot)
            elif match != match:          # no structure rows at all
                bad.append(prot)

        # Per-protein gate. The global averages can pass while one protein is
        # entirely corrupt, so each protein is judged on its own.
        if bad:
            before = len(df)
            df = df[~df["protein"].isin(bad)]
            print(f"\n  DROPPED {len(bad)} protein(s) failing verification: "
                  f"{bad}")
            print(f"  removed {before - len(df)} rows whose burial could not "
                  f"be trusted")

        overall_cov = float(df["burial"].notna().mean())
        have = df.dropna(subset=["_aa_struct"])
        overall_match = (float((have["wildtype"] == have["_aa_struct"]).mean())
                         if len(have) else float("nan"))
        print(f"\n  overall coverage      {overall_cov:.3f}")
        print(f"  overall wt agreement  {overall_match:.3f}")
        if overall_match < 0.9 or overall_cov < 0.5:
            print("\n  *** STOP. The structure's residue disagrees with the "
                  "DMS wildtype too\n  often, or coverage is too low. The "
                  "position numbering does not line up,\n  so this feature "
                  "would be noise dressed as structure. Do not train on it.")
        else:
            print("  join verified: every retained protein's structure "
                  "numbering lines up.")
        df = df.drop(columns=["_aa_struct"])
        df = df.dropna(subset=["burial"])
        print(f"  rows retained after requiring burial: {len(df)}")

    print("\n--- per-assay summary ----------------------------------------")
    print(f"{'protein':<36}{'rows':>8}{'sites':>7}{'pos':>7}")
    for p, s in df.groupby("protein", sort=False):
        print(f"{p[:35]:<36}{len(s):>8}{s['site_SARS2'].nunique():>7}"
              f"{s['label'].mean():>7.3f}")

    # The whole point of adding proteins: do they bring NEW feature vectors?
    # Our active descriptors are functions of (site, wildtype, mutant), so
    # count distinct triples -- but note site numbering is per protein, so the
    # triple must be namespaced by protein to mean anything.
    tri_global = df[["site_SARS2", "wildtype", "mutant"]].drop_duplicates()
    tri_scoped = df[["protein", "site_SARS2", "wildtype",
                     "mutant"]].drop_duplicates()
    # Phenotype homogeneity: mixing them is the most likely reason a
    # multi-assay model underperforms, so it is checked rather than assumed.
    if "selection_type" in sel.columns:
        kinds = sorted(set(sel.loc[sel["DMS_id"].isin(df["protein"].unique()),
                                   "selection_type"].astype(str)))
        if len(kinds) > 1:
            print(f"\n  WARNING: {len(kinds)} different phenotypes pooled: "
                  f"{kinds}.\n  The binary label does not mean the same thing "
                  f"across them, which caps\n  achievable AUC. Consider "
                  f"--selection-type to keep one phenotype.")
        else:
            print(f"\n  phenotype: {kinds[0]} (homogeneous)")

    print("\n--- totals ---------------------------------------------------")
    print(f"  assays loaded              {df['protein'].nunique()}")
    print(f"  organisms                  {df['organism'].nunique()}")
    print(f"  rows                       {len(df)}")
    print(f"  distinct (site,wt,mut)     {len(tri_global)}")
    print(f"  distinct per-protein rows  {len(tri_scoped)}")
    print(f"  overall positive rate      {df['label'].mean():.3f}")
    if skipped:
        print(f"  skipped assays             {len(skipped)}: {skipped[:6]}"
              + (" ..." if len(skipped) > 6 else ""))
    print("\n  For comparison, single_mut_effects.csv gives 3802 rows and")
    print(f"  3802 distinct feature vectors. This is "
          f"{len(tri_global) / 3802:.1f}x the distinct feature vectors.")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    cols = OUT_COLS + (["burial"] if "burial" in df.columns else [])
    df[cols].to_csv(args.out, index=False)
    print(f"\nwrote {len(df)} rows -> {args.out}")

    meta = {
        "n_assays": int(df["protein"].nunique()),
        "n_organisms": int(df["organism"].nunique()),
        "n_rows": int(len(df)),
        "polarity": args.polarity,
        "label_meaning": ("1 = mutation TOLERATED (retains function)"
                          if args.polarity == "retain"
                          else "1 = mutation HAS AN EFFECT (disruptive)"),
        "distinct_feature_vectors": int(len(tri_global)),
        "positive_rate": round(float(df["label"].mean()), 4),
        "assays": sorted(df["protein"].unique().tolist()),
        "skipped": skipped,
    }
    side = os.path.splitext(args.out)[0] + "_meta.json"
    with open(side, "w") as fh:
        json.dump(meta, fh, indent=2)
    print(f"wrote {side}")
    print("\nNEXT: train on it with")
    print(f"  python train_vqc.py --panel {args.out} --group-by protein \\")
    print("      --features 4,6,2,5,0 --readout probs --encoding dense "
          "--axes Y,Z --seeds 3")
    print("  (feature 8 = ace2_distance is SARS-CoV-2-only and is dropped "
          "for multi-protein runs)")


if __name__ == "__main__":
    main()
