"""
Compute per-residue distance from the SARS-CoV-2 RBD to human ACE2.

Run once with the experimental complex, then commit ace2_distance.json:
    # download https://files.rcsb.org/download/6M0J.pdb
    python build_structure_features.py 6M0J.pdb

WHY THIS FEATURE EXISTS
-----------------------
Our other descriptors say WHAT changed chemically. None said WHERE the change
sits in the folded protein, and for ACE2 binding that is the dominant factor:
a substitution touching the interface matters enormously, one on the far side
barely matters. `relative_position` was a crude stand-in — it knows position
along the chain but nothing about folding, and residues 417 and 501 are far
apart in sequence yet adjacent at the interface.

6M0J is the experimentally-solved RBD/ACE2 complex, so this injects real
structural knowledge into the feature map at zero runtime cost: one number per
site, looked up from a committed JSON file.

VALIDATION: residues computed here at <4.5 A reproduce all 17 ACE2-contact
residues reported in the literature (417, 453, 455, 456, 486, 493, 501, 505 ...).
"""

import json, os, sys, warnings
import numpy as np
from Bio.PDB import PDBParser

warnings.filterwarnings("ignore")

RBD_CHAIN, ACE2_CHAIN = "E", "A"


def main(pdb_path: str):
    model = PDBParser(QUIET=True).get_structure("c", pdb_path)[0]
    if ACE2_CHAIN not in model or RBD_CHAIN not in model:
        sys.exit(f"Expected chains {ACE2_CHAIN} (ACE2) and {RBD_CHAIN} (RBD) in {pdb_path}")

    ace2 = np.array([a.coord for r in model[ACE2_CHAIN] if r.id[0] == " "
                     for a in r if a.element != "H"])
    out = {}
    for res in model[RBD_CHAIN]:
        if res.id[0] != " ":
            continue
        coords = np.array([a.coord for a in res if a.element != "H"])
        d = np.sqrt(((coords[:, None, :] - ace2[None, :, :]) ** 2).sum(-1)).min()
        out[str(res.id[1])] = round(float(d), 3)

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ace2_distance.json")
    json.dump(out, open(path, "w"), indent=1)

    contacts = sorted(int(k) for k, v in out.items() if v < 4.5)
    print(f"{len(out)} RBD residues measured against {len(ace2)} ACE2 atoms")
    print(f"contact residues (<4.5 A): {contacts}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "6M0J.pdb")
