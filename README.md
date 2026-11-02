# PhytoBridge

**An evidence explorer bridging traditional medicinal plant knowledge to phytochemical and published scientific evidence.**

Built for [EthnoHack 2026](https://ethnohack2026.devpost.com) (Digital Health & Phytotherapy track).

## What it does

PhytoBridge takes a medicinal plant's recorded traditional uses and lays them beside
the phytochemical constituents recorded for that plant, so you can see, use by use,
what recorded evidence stands behind the claim and where to verify it.

- **Traditional layer**: every recorded ethnobotanical use, with the country of record
  and the source citation where the database provides one.
- **Science layer**: the constituents recorded for the plant and the biological
  activities recorded for each constituent.
- **Bridge view**: each use is matched against constituent activities and labelled
  Strong / Moderate / None recorded. Matches are labelled *direct* or *related* and
  are never presented as proof of efficacy.
- **Verify**: every claim carries a PubMed link-out.

## Data

All data comes from **Dr. Duke's Phytochemical and Ethnobotanical Databases**
(USDA Agricultural Research Service), a public-domain US government work, distributed
as open data via [Ag Data Commons](https://agdatacommons.nal.usda.gov/articles/dataset/Dr_Duke_s_Phytochemical_and_Ethnobotanical_Databases/24660351)
and [Zenodo](https://zenodo.org/records/8118154). Tables used: FNFTAX, FARMACY_NEW,
COMMON_NAMES, ETHNOBOT, AGGREGAC, ACTIVITIES, REFERENCES.

Current dataset: 2,376 plants, 82,873 traditional use records, 104,388 plant–chemical
links, 28,929 chemical activity records.

## Reproduce

```bash
python3 pipeline/build_db.py   # downloads sources, rebuilds data/phytobridge.db
pip install -r requirements.txt
gunicorn app:app --bind 0.0.0.0:$PORT
```

## Stack

Python, Flask, SQLite, vanilla HTML/CSS. No API keys, no paid services.

## Limitations

See `/about` in the app. In short: this is a research prototype. It maps recorded
claims to recorded evidence and never asserts efficacy, safety, or dosage advice.

## Licence

Code: MIT. Data: public domain (USDA).
