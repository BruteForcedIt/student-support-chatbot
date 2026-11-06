"""Tests for staff accounts: Hub staff (admin) and lecturer (reviewer) roles, managing accounts, passwords.
Fake chat model; no LM Studio needed."""
import pytest
from fastapi.testclient import TestClient

from backend import auth, llm
from backend.main import app

ADMIN_PASSWORD = "carol-admin-password"
LECTURER_PASSWORD = "dave-lecturer-password"
REVIEW = {"question": "How do I pay my fees?", "answer": "Use NottinghamHub.", "language": "en",
          "accuracy": 4, "completeness": 3, "clarity": 5, "tone": 5, "safe": True}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        try:
            auth.create_user("carol", ADMIN_PASSWORD)
        except ValueError:
            pass
        yield c


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda messages, **kw: "Use NottinghamHub [1].")


def login(client, username, password):
    r = client.post("/admin/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()


def test_lecturer_account_can_only_review(client):
    admin, me = login(client, "carol", ADMIN_PASSWORD)
    assert me["role"] == "admin"
    made = client.post("/admin/users", headers=admin,
                       json={"username": "dave", "password": LECTURER_PASSWORD, "role": "reviewer"})
    assert made.status_code == 200 and made.json()["role"] == "reviewer"
    again = client.post("/admin/users", headers=admin, json={"username": "DAVE", "password": LECTURER_PASSWORD})
    assert again.status_code == 409                                  # sign-in ignores case, so this is a duplicate
    assert client.post("/admin/users", headers=admin, json={"username": "eve", "password": "short"}).status_code == 400

    lecturer, me = login(client, "Dave", LECTURER_PASSWORD)
    assert me["role"] == "reviewer" and me["username"] == "dave"
    assert client.get("/admin/me", headers=lecturer).json()["role_label"] == "Lecturer"
    for method, path in [("get", "/admin/documents"), ("get", "/admin/stats"), ("get", "/admin/audit"),
                         ("get", "/admin/analytics"), ("get", "/admin/ethics"), ("get", "/admin/users"),
                         ("post", "/admin/reindex"), ("delete", "/admin/documents/abc"), ("delete", "/admin/users/carol")]:
        assert getattr(client, method)(path, headers=lecturer).status_code == 403, path
    upload = client.post("/admin/documents", headers=lecturer,
                         files={"file": ("a.txt", b"some text that is long enough", "text/plain")})
    assert upload.status_code == 403

    assert client.post("/admin/reviews/ask", headers=lecturer, json={"question": "How do I pay fees?"}).status_code == 200
    assert client.post("/admin/reviews", headers=lecturer, json=REVIEW).status_code == 200
    assert client.post("/admin/reviews", headers=admin, json={**REVIEW, "accuracy": 2}).status_code == 200
    mine = client.get("/admin/reviews", headers=lecturer).json()
    assert mine and {r["reviewer"] for r in mine} == {"dave"}       # lecturers only see their own reviews
    assert {"carol", "dave"} <= {r["reviewer"] for r in client.get("/admin/reviews", headers=admin).json()}
    summary = client.get("/admin/reviews/summary", headers=lecturer).json()
    assert summary["staff_by_role"]["reviewer"]["accuracy"] == 4.0   # lecturers' and Hub staff's scores kept apart
    assert summary["staff_by_role"]["admin"]["count"] >= 1 and summary["students"]["reason_labels"]


def test_removing_an_account_signs_it_out(client):
    admin, _ = login(client, "carol", ADMIN_PASSWORD)
    client.post("/admin/users", headers=admin, json={"username": "frank", "password": LECTURER_PASSWORD, "role": "reviewer"})
    frank, _ = login(client, "frank", LECTURER_PASSWORD)
    assert client.get("/admin/me", headers=frank).status_code == 200
    assert "frank" in [u["username"] for u in client.get("/admin/users", headers=admin).json()["users"]]
    assert client.delete("/admin/users/frank", headers=admin).status_code == 200
    assert client.get("/admin/me", headers=frank).status_code == 401
    assert client.delete("/admin/users/frank", headers=admin).status_code == 404
    assert client.delete("/admin/users/carol", headers=admin).status_code == 409      # never your own account
    actions = {a["action"] for a in client.get("/admin/audit", headers=admin).json()}
    assert {"add_user", "remove_user"} <= actions


def test_change_password_signs_out_other_sessions(client):
    admin, _ = login(client, "carol", ADMIN_PASSWORD)
    client.post("/admin/users", headers=admin, json={"username": "grace", "password": LECTURER_PASSWORD, "role": "reviewer"})
    laptop, _ = login(client, "grace", LECTURER_PASSWORD)
    phone, _ = login(client, "grace", LECTURER_PASSWORD)
    new = "grace-new-password"
    wrong = client.post("/admin/me/password", headers=laptop, json={"current_password": "nope", "new_password": new})
    assert wrong.status_code == 400
    short = client.post("/admin/me/password", headers=laptop, json={"current_password": LECTURER_PASSWORD, "new_password": "short"})
    assert short.status_code == 400
    ok = client.post("/admin/me/password", headers=laptop, json={"current_password": LECTURER_PASSWORD, "new_password": new})
    assert ok.status_code == 200
    assert client.get("/admin/me", headers=laptop).status_code == 200     # this session stays signed in
    assert client.get("/admin/me", headers=phone).status_code == 401      # the others are signed out
    assert client.post("/admin/login", json={"username": "grace", "password": LECTURER_PASSWORD}).status_code == 401
    login(client, "grace", new)
