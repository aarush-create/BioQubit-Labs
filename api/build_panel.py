"""
Build reference_panel.json from REAL sequences fetched from NCBI.

Run this once on your own machine (it needs network access to NCBI), then
commit the resulting reference_panel.json:

    python build_panel.py

Why this exists
---------------
The old pathogen_db.json carried hand-written "vector" values, and the
sentinel generated new ones by SHA-256 hashing the accession number. Both are
arbitrary numbers presented as biology. Here every vector is computed from
the actual protein sequence by the same featuriser used at inference time.

Accessions below are the receptor-binding / fusion surface proteins, since
that is what the descriptors are meant to characterise. VERIFY each one
against its label before you present it -- the original database had
NC_045512.2 (Wuhan-Hu-1 reference) labelled as Omicron XBB.1.5, and an
NM_-prefixed accession (an mRNA RefSeq, not a viral genome) for H5N1.
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

import features as feat

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# name -> (protein accession, pdb id, transmission route)
# Each entry is a PROTEIN accession so no translation step is needed.
PANEL = {
    "SARS-CoV-2 spike (Wuhan-Hu-1 reference)": ("YP_009724390.1", "6m0j", "Aerosol / respiratory"),
    "SARS-CoV spike (Tor2)": ("NP_828851.1", "5xlr", "Respiratory droplet"),
    "MERS-CoV spike": ("YP_009047204.1", "4kr0", "Respiratory droplet / zoonotic"),
    "Influenza A H5N1 haemagglutinin": ("ABP51969.1", "2fk0", "Direct contact / droplet"),
    "Influenza A H1N1 haemagglutinin": ("ACP44189.1", "3lzg", "Respiratory droplet"),
    "Ebola virus glycoprotein (Zaire)": ("NP_066246.1", "5kqv", "Direct fluid contact"),
    "Marburg virus glycoprotein": ("YP_001531156.1", "6bp2", "Direct fluid contact"),
    "Nipah virus G attachment glycoprotein": ("NP_112027.1", "7t9l", "Contaminated food / respiratory"),
    "Zika virus envelope polyprotein": ("YP_009428568.1", "5ire", "Vector-borne (Aedes)"),
}


def fetch_protein(accession: str) -> str:
    params = {"db": "protein", "id": accession, "rettype": "fasta", "retmode": "text"}
    # NCBI asks for an email/tool identifier; be a good citizen.
    if os.getenv("NCBI_EMAIL"):
        params["email"] = os.getenv("NCBI_EMAIL")
    params["tool"] = "q-vira"
    with httpx.Client(timeout=30) as client:
        resp = client.get(EUTILS, params=params)
    resp.raise_for_status()
    text = resp.text.strip()
    if not text.startswith(">"):
        raise RuntimeError(f"Unexpected response for {accession}: {text[:120]}")
    return text


def main():
    panel, failures = {}, []
    for name, (acc, pdb, route) in PANEL.items():
        try:
            fasta = fetch_protein(acc)
            angles, explain = feat.featurise(fasta)
            panel[name] = {
                "ncbi_accession": acc,
                "pdb_id": pdb,
                "transmission": route,
                "vector": [round(a, 5) for a in angles],
                "descriptors": explain["descriptors"],
                "sequence_length": explain["length"],
                # Stored so the API can serve it as a reference for variant
                # scoring. Real sequence from NCBI -- never hand-written.
                "sequence": feat.parse_fasta(fasta),
                "source": "NCBI efetch (protein)",
                "featuriser": explain["method"],
                "retrieved": time.strftime("%Y-%m-%d"),
            }
            print(f"ok   {name}  ({explain['length']} aa)")
        except Exception as exc:
            failures.append((name, acc, f"{type(exc).__name__}: {exc}"))
            print(f"FAIL {name} [{acc}]: {type(exc).__name__}")
        # NCBI rate limit without an API key is 3 requests/second.
        time.sleep(0.4)

    if not panel:
        sys.exit("No entries retrieved -- check your network connection.")

    out = os.path.join(os.path.dirname(__file__), "reference_panel.json")
    with open(out, "w") as fh:
        json.dump(panel, fh, indent=2)
    print(f"\nWrote {len(panel)} entries to {out}")
    if failures:
        print("\nFailed (fix the accession or drop the entry -- do NOT invent a vector):")
        for name, acc, err in failures:
            print(f"  {name} [{acc}]: {err}")


if __name__ == "__main__":
    main()
