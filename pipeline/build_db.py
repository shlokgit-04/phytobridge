"""PhytoBridge data pipeline.

Downloads the public-domain source tables of Dr. Duke's Phytochemical and
Ethnobotanical Databases (USDA ARS), then reconstructs the SQLite database
the app serves. Run from the repository root:

    python3 pipeline/build_db.py

Sources:
- Zenodo cleaned tables (COMMON_NAMES): records 8118154, 8118174, 8118186, 8118194
- Ag Data Commons (figshare) archival zip with the full raw table set:
  article 24660351 (Duke-Source-CSV.zip)

Licence note: the underlying USDA database is public domain (US government
work). The Zenodo cleaning steps were published openly; see the records.
"""
import csv
import io
import os
import sqlite3
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
DB = os.path.join(ROOT, "data", "phytobridge.db")

ZENODO = {
    "COMMON_NAMES.csv": "https://zenodo.org/api/records/8118186/files/Cleaned_COMMON_NAMES.csv/content",
    "ETHNOBOT.csv": "https://zenodo.org/api/records/8118194/files/Cleaned_ETHNOBOT.csv/content",
}
DUKE_ZIP_URL = "https://ndownloader.figshare.com/files/43363335"


def fetch(url, dest):
    if os.path.exists(dest):
        return
    print("fetching", url)
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())


def ensure_sources():
    os.makedirs(RAW, exist_ok=True)
    for name, url in ZENODO.items():
        fetch(url, os.path.join(RAW, name))
    zpath = os.path.join(RAW, "Duke-Source-CSV.zip")
    fetch(DUKE_ZIP_URL, zpath)
    ddir = os.path.join(RAW, "duke")
    if not os.path.isdir(ddir):
        zipfile.ZipFile(zpath).extractall(ddir)
    return os.path.join(RAW, ""), ddir


def clean(v):
    return (v or "").strip()


def build():
    root, duke = ensure_sources()
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.executescript("""
CREATE TABLE plants(fnfnum INTEGER PRIMARY KEY, taxon TEXT, genus TEXT, species TEXT, family TEXT, plco TEXT);
CREATE TABLE common_names(fnfnum INTEGER, name TEXT);
CREATE TABLE plant_chems(fnfnum INTEGER, chem TEXT, chemid TEXT, ref TEXT);
CREATE TABLE ethno_uses(taxon TEXT, genus TEXT, species TEXT, use TEXT, cname TEXT, country TEXT, ref TEXT, longref TEXT);
CREATE TABLE chem_activities(chem TEXT, activity TEXT, dosage TEXT, ref TEXT, longref TEXT);
CREATE TABLE refs(ref TEXT PRIMARY KEY, longref TEXT);
CREATE INDEX idx_pc ON plant_chems(fnfnum);
CREATE INDEX idx_eu ON ethno_uses(taxon);
CREATE INDEX idx_ca ON chem_activities(chem);
""")

    def insert(sql, args, dedupe=False):
        cur.execute(("INSERT OR IGNORE INTO " if dedupe else "INSERT INTO ") + sql, args)

    for row in csv.DictReader(open(f"{duke}/FNFTAX.csv", encoding="utf-8", errors="replace")):
        fnf = clean(row["FNFNUM"])
        if fnf.isdigit():
            insert("plants VALUES(?,?,?,?,?,?)", (int(fnf), clean(row["TAXON"]), clean(row["GENUS"]), clean(row["SPECIES"]), clean(row["FAMILY"]), clean(row["PLCO"])), True)

    for row in csv.DictReader(open(f"{root}COMMON_NAMES.csv", encoding="utf-8", errors="replace")):
        fnf = clean(row.get("FNFNUM", ""))
        if fnf.isdigit():
            insert("common_names VALUES(?,?)", (int(fnf), clean(row["CNNAM"])), True)

    for row in csv.DictReader(open(f"{duke}/FARMACY_NEW.csv", encoding="utf-8", errors="replace")):
        fnf, chem = clean(row["FNFNUM"]), clean(row["CHEM"])
        if fnf.isdigit() and chem:
            insert("plant_chems VALUES(?,?,?,?)", (int(fnf), chem, clean(row.get("CHEMID", "")), clean(row.get("REFERENCE", ""))), True)

    for row in csv.DictReader(open(f"{duke}/REFERENCES.csv", encoding="utf-8", errors="replace")):
        insert("refs VALUES(?,?)", (clean(row["REFERENCE"]), clean(row["LONGREF"])))

    for row in csv.DictReader(open(f"{root}ETHNOBOT.csv", encoding="utf-8", errors="replace")):
        g, s, act = clean(row["GENUS"]), clean(row["SPECIES"]), clean(row["ACTIVITY"])
        if not s or not act:
            continue
        refid = clean(row["REFERENCE"])
        longref = ""
        if refid:
            cur.execute("SELECT longref FROM refs WHERE ref=?", (refid,))
            r = cur.fetchone()
            longref = r[0] if r else ""
        insert("ethno_uses VALUES(?,?,?,?,?,?,?,?)", (f"{g} {s}", g, s, act, clean(row["CNAME"]), clean(row["COUNTRY"]), refid, longref))

    for row in csv.DictReader(open(f"{duke}/AGGREGAC.csv", encoding="utf-8", errors="replace")):
        chem, act = clean(row["CHEM"]), clean(row["ACTIVITY"])
        if not chem or not act:
            continue
        refid = clean(row["REFERENCE"])
        longref = ""
        if refid:
            cur.execute("SELECT longref FROM refs WHERE ref=?", (refid,))
            r = cur.fetchone()
            longref = r[0] if r else ""
        insert("chem_activities VALUES(?,?,?,?,?)", (chem, act, clean(row["DOSAGE"]), refid, longref))

    con.commit()
    for t in ["plants", "common_names", "plant_chems", "ethno_uses", "chem_activities", "refs"]:
        print(t, cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    con.close()


if __name__ == "__main__":
    build()
