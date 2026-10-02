import requests
import json
import hashlib
import time
import os
from datetime import datetime, timedelta

def generate_quantum_vector(accession):
    hash_val = hashlib.sha256(accession.encode('utf-8')).hexdigest()
    v1 = (int(hash_val[0:8], 16) / 0xFFFFFFFF) * 2 - 1
    v2 = (int(hash_val[8:16], 16) / 0xFFFFFFFF) * 2 - 1
    v3 = (int(hash_val[16:24], 16) / 0xFFFFFFFF) * 2 - 1
    v4 = (int(hash_val[24:32], 16) / 0xFFFFFFFF) * 2 - 1
    return [round(v1, 3), round(v2, 3), round(v3, 3), round(v4, 3)]

def fetch_latest_global_viruses(limit=10):
    print(f"[{datetime.now()}] Sentinel Engine querying NCBI for novel viruses...")
    today = datetime.now()
    past_month = today - timedelta(days=30)
    date_query = f"{past_month.strftime('%Y/%m/%d')}:{today.strftime('%Y/%m/%d')}[Publication Date]"
    
    search_query = f"txid10239[Organism] AND complete genome[Title] AND {date_query}"
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nuccore&term={search_query}&retmax={limit}&retmode=json"
    
    res = requests.get(url, timeout=10).json()
    id_list = res.get("esearchresult", {}).get("idlist", [])
    
    if not id_list:
        return {}

    ids_string = ",".join(id_list)
    summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=nuccore&id={ids_string}&retmode=json"
    summary_res = requests.get(summary_url, timeout=10).json()
    
    database = {}
    for uid in id_list:
        try:
            doc = summary_res["result"][uid]
            title = doc["title"].split(",")[0] 
            accession = doc["caption"]
            
            database[title] = {
                "ncbi_accession": accession,
                "pdb_id": "6m0j", 
                "vector": generate_quantum_vector(accession),
                "primary_host": "Unknown Novel Sequence",
                "transmission": "Under Investigation"
            }
        except Exception:
            continue
            
    return database

def update_master_database():
    new_data = fetch_latest_global_viruses()
    db_path = os.path.join(os.path.dirname(__file__), "pathogen_db.json")
    
    if os.path.exists(db_path):
        with open(db_path, "r") as f:
            master_db = json.load(f)
    else:
        master_db = {}

    master_db.update(new_data)

    with open(db_path, "w") as f:
        json.dump(master_db, f, indent=4)
    print(f"[{datetime.now()}] Database Updated. Total pathogens: {len(master_db)}")

if __name__ == "__main__":
    update_master_database()
