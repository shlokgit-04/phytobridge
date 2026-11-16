import os
import sqlite3

from conftest import *  # noqa: F401,F403

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _user(tmp_app, email):
    c = tmp_app.test_client()
    r = c.post("/api/auth/register", json={"email": email, "password": "Str0ngPass!x"})
    return c, r.get_json()["token"]


def _first_plant():
    db = sqlite3.connect(os.path.join(ROOT, "data", "phytobridge.db"))
    fnf = db.execute("SELECT rowid FROM plants LIMIT 1").fetchone()[0]
    db.close()
    return fnf


def test_saved_flow(tmp_app):
    app = tmp_app
    c, tok = _user(app, "s@example.com")
    h = {"Authorization": f"Bearer {tok}"}
    fnf = _first_plant()
    assert c.post("/api/saved", json={"fnfnum": fnf}, headers=h).get_json()["status"] == "saved"
    assert c.post("/api/saved", json={"fnfnum": fnf}, headers=h).get_json()["status"] == "already_saved"
    lst = c.get("/api/saved", headers=h).get_json()["items"]
    assert [s["fnfnum"] for s in lst] == [fnf]
    assert c.post(f"/api/saved/{fnf}/note", json={"note": "check berberine studies"}, headers=h).status_code == 200
    lst = c.get("/api/saved", headers=h).get_json()["items"]
    assert lst[0]["note"] == "check berberine studies"
    assert c.delete(f"/api/saved/{fnf}", headers=h).status_code == 200
    assert c.get("/api/saved", headers=h).get_json()["items"] == []


def test_saved_rejects_unknown_plant_and_strangers(tmp_app):
    app = tmp_app
    c, tok = _user(app, "v@example.com")
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/saved", json={"fnfnum": 999999999}, headers=h).status_code == 404
    assert c.get("/api/saved").status_code == 401
    c2, tok2 = _user(app, "w@example.com")
    assert c2.get("/api/saved", headers={"Authorization": f"Bearer {tok2}"}).get_json()["items"] == []


def test_note_length_cap(tmp_app):
    app = tmp_app
    c, tok = _user(app, "n@example.com")
    h = {"Authorization": f"Bearer {tok}"}
    fnf = _first_plant()
    c.post("/api/saved", json={"fnfnum": fnf}, headers=h)
    assert c.post(f"/api/saved/{fnf}/note", json={"note": "x" * 2001}, headers=h).status_code == 400
