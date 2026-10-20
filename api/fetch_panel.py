import os, urllib.request

os.makedirs("data", exist_ok=True)
FILES = {
    "variants": "https://media.githubusercontent.com/media/jbloomlab/SARS-CoV-2-RBD_DMS_variants/main/results/final_variant_scores/final_variant_scores.csv",
    "omicron":  "https://media.githubusercontent.com/media/jbloomlab/SARS-CoV-2-RBD_DMS_Omicron/main/results/final_variant_scores/final_variant_scores.csv",
}
for name, url in FILES.items():
    out = f"data/final_variant_scores_{name}.csv"
    print(f"downloading {name} ...")
    urllib.request.urlretrieve(url, out)
    size = os.path.getsize(out)
    print(f"  -> {out}  ({size:,} bytes)")
    if size < 4096:
        print("  WARNING: suspiciously small, probably an LFS pointer or error page")
print("done")