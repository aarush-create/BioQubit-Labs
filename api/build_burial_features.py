"""
build_burial_features.py -- a protein-agnostic structural feature.

WHY
---
ace2_distance is the strongest single descriptor we have: 0.7143 AUC alone, and
adding it moved the VQC from 0.682 to 0.747. But it is measured from ONE
complex (6M0J, SARS-CoV-2 RBD bound to ACE2), so it means nothing for any other
protein. On the multi-protein panel we had to drop it, and the model fell to
~0.63 -- it was left with five descriptors that say WHICH residue changed and
nothing about WHERE.

This computes the generalizable version: how BURIED each residue is in its own
folded structure. Buried residues are packed against the rest of the protein,
so substituting them is usually disruptive; exposed ones are usually tolerated.
It is computable for every protein from its structure alone, needs no binding
partner, and plays the same role ace2_distance played -- giving the model
positional context.

WHAT IT MEASURES
----------------
Contact number: for each residue, how many OTHER residues have a representative
atom within R angstroms. A standard burial proxy, strongly correlated with
relative solvent accessibility but computable without an SASA implementation.

The representative atom is CB (the first side-chain carbon), falling back to CA
for glycine, which has no CB. Using CB rather than CA points the measurement
along the side chain, which is what actually gets packed.

Three radii are written (8, 10, 13 A) so the feature can be chosen by
measurement rather than guessed. 10 A is the usual default.

NO BIOPYTHON NEEDED
-------------------
PDB ATOM records are fixed-column, so they are parsed directly. mmCIF is also
handled, via the atom_site loop. Both are tried per file.

UNVERIFIED: the layout inside ProteinGym_AF2_structures.zip
-----------------------------------------------------------
I could not download that archive (the host is blocked from where this was
written), so the mapping from assay to structure file is inferred, not checked.
Run with --dry-run FIRST: it reports what it found and how it matched, without
writing anything. If the matching is wrong, the fix is one line in
_match_structures and the dry run will make it obvious.

Usage
-----
    python build_burial_features.py --af2-dir ../af2 \
        --index ../DMS_substitutions.csv --dry-run

    python build_burial_features.py --af2-dir ../af2 \
        --index ../DMS_substitutions.csv --out burial.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

RADII = (8.0, 10.0, 13.0)

# 3-letter -> 1-letter, so the join can CHECK that the structure's residue at a
# position matches the DMS table's wildtype. AF2 models are numbered over the
# full UniProt sequence; if the DMS positions carry any offset, every row would
# silently get the wrong residue's burial. Emitting the residue identity turns
# that from an invisible corruption into a measurable mismatch rate.
THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}
STRUCT_EXT = (".pdb", ".cif", ".mmcif", ".ent")


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------- parsing
def parse_pdb(path: str):
    """PDB ATOM records are fixed-column; see the PDB format spec.
        name   cols 13-16, resName 18-20, chain 22, resSeq 23-26,
        x 31-38, y 39-46, z 47-54
    Returns {resseq: (resname, np.array([x,y,z]))} for the representative atom.
    """
    best: dict[int, tuple[str, np.ndarray, str]] = {}
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            if not line.startswith(("ATOM  ", "HETATM")):
                continue
            name = line[12:16].strip()
            if name not in ("CA", "CB"):
                continue
            try:
                resseq = int(line[22:26])
                xyz = np.array([float(line[30:38]), float(line[38:46]),
                                float(line[46:54])])
            except ValueError:
                continue
            resname = line[17:20].strip()
            # CB wins over CA; CA only kept if no CB (glycine, or truncated)
            if resseq in best and best[resseq][2] == "CB":
                continue
            best[resseq] = (resname, xyz, name)
    return {k: (v[0], v[1]) for k, v in best.items()}


def parse_cif(path: str):
    """mmCIF atom_site loop. Column order varies, so the header is read."""
    cols: list[str] = []
    rows: list[list[str]] = []
    in_loop = False
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            t = line.strip()
            if t.startswith("_atom_site."):
                cols.append(t.split(".", 1)[1].split()[0])
                in_loop = True
                continue
            if in_loop:
                if t.startswith(("#", "loop_", "_")) or not t:
                    if cols and rows:
                        break
                    continue
                parts = t.split()
                if len(parts) >= len(cols):
                    rows.append(parts[:len(cols)])
    if not cols or not rows:
        return {}
    try:
        i_name = cols.index("label_atom_id")
        i_comp = cols.index("label_comp_id")
        i_seq = cols.index("label_seq_id")
        ix, iy, iz = (cols.index("Cartn_x"), cols.index("Cartn_y"),
                      cols.index("Cartn_z"))
    except ValueError:
        return {}

    best: dict[int, tuple[str, np.ndarray, str]] = {}
    for r in rows:
        name = r[i_name].strip('"')
        if name not in ("CA", "CB"):
            continue
        try:
            resseq = int(r[i_seq])
            xyz = np.array([float(r[ix]), float(r[iy]), float(r[iz])])
        except ValueError:
            continue
        if resseq in best and best[resseq][2] == "CB":
            continue
        best[resseq] = (r[i_comp], xyz, name)
    return {k: (v[0], v[1]) for k, v in best.items()}


def load_structure(path: str):
    if path.lower().endswith(".cif") or path.lower().endswith(".mmcif"):
        res = parse_cif(path)
        return res or parse_pdb(path)
    res = parse_pdb(path)
    return res or parse_cif(path)


def contact_numbers(res: dict) -> dict:
    """Residues within each radius, excluding self, plus the residue identity
    so the downstream join can verify position numbering."""
    if not res:
        return {}
    keys = sorted(res)
    xyz = np.array([res[k][1] for k in keys])
    d = np.linalg.norm(xyz[:, None, :] - xyz[None, :, :], axis=-1)
    np.fill_diagonal(d, np.inf)
    out = {}
    for i, k in enumerate(keys):
        rec = {f"cn{int(r)}": int((d[i] < r).sum()) for r in RADII}
        rec["aa"] = THREE_TO_ONE.get(res[k][0].upper(), "X")
        out[int(k)] = rec
    return out


# --------------------------------------------------------------- matching
def _match_structures(af2_dir: str, idx: pd.DataFrame) -> dict:
    """Map DMS_id -> structure path.

    INFERRED, NOT VERIFIED. ProteinGym names structures by UniProt ID in some
    releases and by DMS_id in others, sometimes nested one folder deep. We
    index every structure file by its basename stem and try, in order:
      1. exact DMS_id
      2. exact UniProt_ID
      3. stem that starts with the UniProt_ID (handles suffixes)
    --dry-run prints which rule fired, so a wrong guess is visible immediately.
    """
    found: dict[str, str] = {}
    for root, _d, files in os.walk(af2_dir):
        for f in files:
            if f.lower().endswith(STRUCT_EXT):
                found.setdefault(os.path.splitext(f)[0], os.path.join(root, f))
    if not found:
        die(f"no structure files ({'/'.join(STRUCT_EXT)}) under {af2_dir}")

    stems = list(found)
    mapping, how = {}, {}
    for r in idx.itertuples(index=False):
        did, up = str(r.DMS_id), str(r.UniProt_ID)
        if did in found:
            mapping[did] = found[did]; how[did] = "DMS_id"
        elif up in found:
            mapping[did] = found[up]; how[did] = "UniProt_ID"
        else:
            pre = [s for s in stems if s.startswith(up)]
            if len(pre) == 1:
                mapping[did] = found[pre[0]]; how[did] = "UniProt_ID prefix"
    return mapping, how, found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--af2-dir", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--taxon", default=None)
    ap.add_argument("--selection-type", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what was found and how it matched; write nothing")
    ap.add_argument("--out", default="burial.json")
    args = ap.parse_args()

    if not os.path.isdir(args.af2_dir):
        die(f"--af2-dir {args.af2_dir} is not a directory")
    idx = pd.read_csv(args.index)
    if args.taxon:
        idx = idx[idx["taxon"].astype(str).str.lower() == args.taxon.lower()]
    if args.selection_type:
        idx = idx[idx["selection_type"].astype(str).str.lower()
                  == args.selection_type.lower()]
    if idx.empty:
        die("no assays matched the filters")

    mapping, how, found = _match_structures(args.af2_dir, idx)
    print(f"structure files discovered: {len(found)}")
    print(f"assays requested:           {len(idx)}")
    print(f"assays matched:             {len(mapping)}")
    if how:
        from collections import Counter
        print(f"match rules used:           {dict(Counter(how.values()))}")
    missing = [d for d in idx["DMS_id"] if d not in mapping]
    if missing:
        print(f"UNMATCHED ({len(missing)}): {missing[:8]}"
              + (" ..." if len(missing) > 8 else ""))
        print(f"  sample available stems: {sorted(found)[:6]}")

    if args.dry_run:
        print("\n--dry-run: nothing written. If the match rules or the "
              "unmatched list\nlook wrong, send me this output and I will fix "
              "_match_structures.")
        return

    burial, stats = {}, []
    for did, path in sorted(mapping.items()):
        res = load_structure(path)
        if not res:
            print(f"  {did}: could not parse {os.path.basename(path)}")
            continue
        cn = contact_numbers(res)
        burial[did] = cn
        vals = [v["cn10"] for v in cn.values()]
        stats.append((did, len(cn), float(np.mean(vals)), int(max(vals))))
        print(f"  {did:<36} {len(cn):>5} residues  mean cn10 "
              f"{np.mean(vals):>5.1f}  max {max(vals)}")

    if not burial:
        die("no structures parsed successfully")

    with open(args.out, "w") as fh:
        json.dump(burial, fh)
    print(f"\nwrote {len(burial)} proteins -> {args.out}")
    allv = [v["cn10"] for p in burial.values() for v in p.values()]
    print(f"cn10 across all proteins: min {min(allv)} median "
          f"{int(np.median(allv))} max {max(allv)}")
    print("\nSanity expectation: a buried core residue should score ~15-25 "
          "contacts at\n10 A and a surface residue ~5-10. If everything is "
          "near one value, the\nrepresentative-atom selection is wrong and the "
          "feature will be useless.")


if __name__ == "__main__":
    main()
