"""PhytoBridge: an evidence explorer bridging traditional medicinal plant
knowledge to phytochemical and PubMed evidence.

Data: Dr. Duke's Phytochemical and Ethnobotanical Databases (USDA ARS),
public domain. See pipeline/ for the build and /about in the app.

This app is a research prototype. It does not provide medical advice.
"""
import os
import re
import sqlite3
from flask import Flask, abort, g, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from accounts import (SECRET_KEY, UserStore, check_password, hash_password,
                      rate_limited, valid_email)

DB_PATH = os.environ.get("PHYTOBRIDGE_DB",
                         os.path.join(os.path.dirname(__file__), "data", "phytobridge.db"))

app = Flask(__name__)
store = UserStore()


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"),
}


@app.after_request
def set_security_headers(resp):
    for k, v in _SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    return resp


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


# --------------------------------------------------------------------------
# Accounts, sessions and per-user saved plants
# --------------------------------------------------------------------------
from flask import Request  # noqa: E402
from pydantic import BaseModel  # noqa: E402


def _client_ip() -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[0].strip() if fwd else (request.remote_addr or "?"))


def require(req: Request):
    auth = req.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    user = store.verify(token)
    if user is None:
        raise PermissionError("not signed in")
    return user


class AuthPayload(BaseModel):
    email: str
    password: str


class NotePayload(BaseModel):
    note: str


class SavePayload(BaseModel):
    fnfnum: int
    note: str = ""


@app.post("/api/auth/register")
def api_register():
    if rate_limited(_client_ip()):
        return jsonify(error="too many attempts, try again in a few minutes"), 429
    body = AuthPayload(**(request.get_json(silent=True) or {}))
    if not valid_email(body.email):
        return jsonify(error="enter a valid email address"), 400
    if len(body.password) < 8:
        return jsonify(error="password must be at least 8 characters"), 400
    try:
        uid = store.create_user(body.email, hash_password(body.password))
    except sqlite3.IntegrityError:
        return jsonify(error="an account with this email already exists"), 409
    user = store.user_by_id(uid)
    return jsonify(token=store.issue(uid, user["token_version"]), email=user["email"])


@app.post("/api/auth/login")
def api_login():
    if rate_limited(_client_ip()):
        return jsonify(error="too many attempts, try again in a few minutes"), 429
    body = AuthPayload(**(request.get_json(silent=True) or {}))
    user = store.user_by_email(body.email)
    if user is None or not check_password(body.password, user["pw_hash"]):
        return jsonify(error="wrong email or password"), 401
    return jsonify(token=store.issue(user["id"], user["token_version"]), email=user["email"])


@app.get("/api/auth/me")
def api_me():
    try:
        user = require(request)
    except PermissionError:
        return jsonify(error="not signed in"), 401
    return jsonify(user={"email": user["email"], "created_at": user["created_at"]})


@app.get("/api/auth/export")
def api_export():
    try:
        user = require(request)
    except PermissionError:
        return jsonify(error="not signed in"), 401
    return jsonify(user={"email": user["email"], "created_at": user["created_at"]},
                   saved=store.saved_list(user["id"]))


@app.delete("/api/auth/me")
def api_delete_account():
    try:
        user = require(request)
    except PermissionError:
        return jsonify(error="not signed in"), 401
    store.bump_token_version(user["id"])
    store.delete_user(user["id"])
    return jsonify(status="deleted")


@app.get("/api/saved")
def api_saved_list():
    try:
        user = require(request)
    except PermissionError:
        return jsonify(error="not signed in"), 401
    db = get_db()
    items = []
    for s in store.saved_list(user["id"]):
        p = db.execute("SELECT rowid AS fnfnum, taxon, family FROM plants WHERE rowid = ?",
                       (s["fnfnum"],)).fetchone()
        items.append({"fnfnum": s["fnfnum"], "taxon": p["taxon"] if p else None,
                      "family": p["family"] if p else None,
                      "note": s["note"], "saved_at": s["saved_at"]})
    return jsonify(items=items)


@app.post("/api/saved")
def api_saved_add():
    try:
        user = require(request)
    except PermissionError:
        return jsonify(error="not signed in"), 401
    body = SavePayload(**(request.get_json(silent=True) or {}))
    db = get_db()
    if db.execute("SELECT 1 FROM plants WHERE rowid = ?", (body.fnfnum,)).fetchone() is None:
        return jsonify(error="unknown plant"), 404
    created = store.saved_add(user["id"], body.fnfnum, body.note)
    return jsonify(status="saved" if created else "already_saved")


@app.delete("/api/saved/<int:fnfnum>")
def api_saved_remove(fnfnum):
    try:
        user = require(request)
    except PermissionError:
        return jsonify(error="not signed in"), 401
    if not store.saved_remove(user["id"], fnfnum):
        return jsonify(error="not saved"), 404
    return jsonify(status="removed")


@app.post("/api/saved/<int:fnfnum>/note")
def api_saved_note(fnfnum):
    try:
        user = require(request)
    except PermissionError:
        return jsonify(error="not signed in"), 401
    body = NotePayload(**(request.get_json(silent=True) or {}))
    if len(body.note) > 2000:
        return jsonify(error="note must be at most 2000 characters"), 400
    if not store.saved_set_note(user["id"], fnfnum, body.note):
        return jsonify(error="not saved"), 404
    return jsonify(status="noted")


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/register")
def register_page():
    return render_template("register.html")


@app.route("/saved")
def saved_page():
    return render_template("saved.html")


@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
