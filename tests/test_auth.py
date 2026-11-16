from conftest import *  # noqa: F401,F403
import pytest


def _register(client, email, pw="Str0ngPass!x"):
    return client.post("/api/auth/register", json={"email": email, "password": pw})


def test_register_login_me(tmp_app):
    app = tmp_app
    c = app.test_client()
    r = _register(c, "a@example.com")
    assert r.status_code == 200
    tok = r.get_json()["token"]
    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200
    assert me.get_json()["user"]["email"] == "a@example.com"
    # login with the right password works, wrong password is rejected
    ok = c.post("/api/auth/login", json={"email": "a@example.com", "password": "Str0ngPass!x"})
    assert ok.status_code == 200
    bad = c.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-pass"})
    assert bad.status_code == 401


def test_register_rejects_bad_input(tmp_app):
    app = tmp_app
    c = app.test_client()
    assert _register(c, "not-an-email").status_code == 400
    assert _register(c, "x@example.com", "short").status_code == 400
    assert _register(c, "x@example.com").status_code == 200
    assert _register(c, "x@example.com").status_code == 409  # duplicate


def test_me_requires_token(tmp_app):
    app = tmp_app
    c = app.test_client()
    assert c.get("/api/auth/me").status_code == 401
    assert c.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_token_invalidated_by_delete(tmp_app):
    app = tmp_app
    c = app.test_client()
    tok = _register(c, "del@example.com").get_json()["token"]
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    assert c.delete("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_export_returns_user_data(tmp_app):
    app = tmp_app
    c = app.test_client()
    tok = _register(c, "exp@example.com").get_json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/saved", json={"fnfnum": 1}, headers=h)
    ex = c.get("/api/auth/export", headers=h)
    assert ex.status_code == 200
    data = ex.get_json()
    assert data["user"]["email"] == "exp@example.com"
    assert any(s["fnfnum"] == 1 for s in data["saved"])
