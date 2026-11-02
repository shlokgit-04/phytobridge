"""PhytoBridge: an evidence explorer bridging traditional medicinal plant
knowledge to phytochemical and PubMed evidence.

Data: Dr. Duke's Phytochemical and Ethnobotanical Databases (USDA ARS),
public domain. See pipeline/ for the build and /about in the app.

This app is a research prototype. It does not provide medical advice.
"""
import os
import re
import sqlite3
from flask import Flask, abort, g, render_template, request

DB_PATH = os.environ.get("PHYTOBRIDGE_DB",
                         os.path.join(os.path.dirname(__file__), "data", "phytobridge.db"))

app = Flask(__name__)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA query_only = 1")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


STOP = {"THE", "AND", "OF", "IN", "TO", "FOR", "A", "AN"}


def norm(s):
    s = re.sub(r"[^A-Za-z0-9 ]+", " ", (s or "").upper())
    return re.sub(r"\s+", " ", s).strip()


def tokens(s):
    return [t for t in norm(s).split() if t and t not in STOP]


def match_kind(use, activity):
    """Classify how a traditional use relates to a chemical bioactivity."""
    u, a = norm(use), norm(activity)
    if not u or not a:
        return None
    ut, at = tokens(use), tokens(activity)
    if u == a:
        return "direct"
    if set(ut) & set(at):
        return "direct"
    # stem-ish containment: ANTIDIABETIC ~ DIABETIC, ANALGESIC ~ ANALGESIA
    for x in ut:
        if len(x) >= 4:
            for y in at:
                if len(y) >= 4 and (x.startswith(y[: max(4, len(y) - 2)]) or y.startswith(x[: max(4, len(x) - 2)])):
                    return "related"
    return None


def pubmed(genus, species, extra=""):
    q = "+".join(x for x in [genus, species, extra] if x)
    return f"https://pubmed.ncbi.nlm.nih.gov/?term={q}"


@app.route("/")
def index():
    db = get_db()
    stats = {
        "plants": db.execute("SELECT COUNT(*) FROM plants").fetchone()[0],
        "uses": db.execute("SELECT COUNT(*) FROM ethno_uses").fetchone()[0],
        "plant_chems": db.execute("SELECT COUNT(DISTINCT fnfnum || ':' || chem) FROM plant_chems").fetchone()[0],
        "chem_acts": db.execute("SELECT COUNT(*) FROM chem_activities").fetchone()[0],
    }
    featured = db.execute(
        "SELECT p.rowid AS fnfnum, p.taxon, p.family, COUNT(e.use) AS uses "
        "FROM plants p JOIN ethno_uses e ON e.taxon = p.taxon "
        "GROUP BY p.rowid ORDER BY uses DESC LIMIT 6").fetchall()
    return render_template("index.html", stats=stats, featured=featured)


@app.route("/search")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return render_template("search.html", q=q, results=[])
    like = f"%{norm(q)}%"
    db = get_db()
    rows = db.execute(
        "SELECT p.rowid AS fnfnum, p.taxon, p.family, GROUP_CONCAT(DISTINCT c.name) AS common "
        "FROM plants p LEFT JOIN common_names c ON c.fnfnum = p.rowid "
        "WHERE UPPER(p.taxon) LIKE ? OR UPPER(c.name) LIKE ? "
        "GROUP BY p.rowid ORDER BY p.taxon LIMIT 60",
        (like, like)).fetchall()
    return render_template("search.html", q=q, results=rows)


@app.route("/plant/<int:fnfnum>")
def plant(fnfnum):
    db = get_db()
    p = db.execute("SELECT rowid AS fnfnum, * FROM plants WHERE rowid = ?", (fnfnum,)).fetchone()
    if p is None:
        abort(404)
    common = [r[0] for r in db.execute("SELECT name FROM common_names WHERE fnfnum = ? ORDER BY name", (fnfnum,))]
    chems = [r[0] for r in db.execute("SELECT DISTINCT chem FROM plant_chems WHERE fnfnum = ? ORDER BY chem", (fnfnum,))]
    uses = db.execute(
        "SELECT use, country, ref, longref FROM ethno_uses WHERE taxon = ? ORDER BY use",
        (p["taxon"],)).fetchall()
    n_chems = len(chems)
    if n_chems and len(chems) <= 600:
        placeholders = ",".join("?" * n_chems)
        act_rows = db.execute(
            f"SELECT chem, activity, dosage, longref FROM chem_activities WHERE chem IN ({placeholders})",
            chems).fetchall()
        chem_acts = {}
        for r in act_rows:
            chem_acts.setdefault(r["chem"], []).append((r["activity"], r["dosage"], r["longref"]))
    else:
        chem_acts = {}
    # Build the bridge: for every recorded use, which plant chemicals carry a
    # matching bioactivity?
    bridge = []
    for u in uses:
        matches = {}
        for chem, acts in chem_acts.items():
            kinds = {match_kind(u["use"], a[0]) for a in acts}
            kinds.discard(None)
            if kinds:
                support = [a[0] for a in acts if match_kind(u["use"], a[0])]
                matches[chem] = support
        n_support = len(matches)
        if n_support >= 3:
            tier = "strong"
        elif n_support >= 1:
            tier = "moderate"
        else:
            tier = "none"
        bridge.append({"use": u, "matches": matches, "tier": tier, "n": n_support})
    bridge.sort(key=lambda b: (-b["n"], b["use"]["use"]))
    return render_template("plant.html", p=p, common=common, chems=chems,
                           bridge=bridge, pubmed=pubmed)


@app.route("/use/<path:use>")
def use_page(use):
    db = get_db()
    want = norm(use)
    rows = db.execute(
        "SELECT DISTINCT taxon FROM ethno_uses WHERE UPPER(use) = ?", (want,)).fetchall()
    if not rows:
        like = f"%{want}%"
        rows = db.execute(
            "SELECT DISTINCT taxon FROM ethno_uses WHERE UPPER(use) LIKE ? LIMIT 40",
            (like,)).fetchall()
    plants = []
    for r in rows:
        p = db.execute(
            "SELECT p.rowid AS fnfnum, p.taxon, p.family, COUNT(e.use) AS uses "
            "FROM plants p LEFT JOIN ethno_uses e ON e.taxon = p.taxon "
            "WHERE p.taxon = ? GROUP BY p.rowid", (r["taxon"],)).fetchone()
        if p is not None:
            plants.append(p)
    plants.sort(key=lambda x: -x["uses"])
    return render_template("use.html", use=use, plants=plants)


@app.route("/about")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
