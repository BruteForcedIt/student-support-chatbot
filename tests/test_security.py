"""Tests for the web-security layer: safety headers, CORS, request size limits, input limits,
sign-in rate limit, hidden files, API docs switch and safe document replacement. No LM Studio needed."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from backend import auth, config, ingest, llm, main, security, service
from backend.main import app

PASSWORD = "correct-horse-battery"
DOC_V1 = "Library opening hours are 8am to 10pm on weekdays. Bring your student card to enter the library."
DOC_V2 = "Library opening hours are 9am to 9pm on weekdays. Bring your student card to enter the library."


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        try:
            auth.create_user("sec-admin", PASSWORD)
        except ValueError:
            pass
        yield c


@pytest.fixture(scope="module")
def headers(client):
    r = client.post("/admin/login", json={"username": "sec-admin", "password": PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda messages, **kw: "Weekdays 8am to 10pm [1].")
    main._recent.clear()
    yield
    main._recent.clear()


def test_safety_headers_and_framing_rules(client, headers):
    page = client.get("/app/index.html")
    assert page.status_code == 200
    csp = page.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp
    assert f"frame-ancestors {config.FRAME_ANCESTORS}" in csp      # the widget may frame the chat page
    assert "x-frame-options" not in page.headers
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "microphone=(self)" in page.headers["permissions-policy"]
    assert "strict-transport-security" not in page.headers          # plain http: no HSTS

    for path in ("/app/admin.html", "/health", "/app//admin.html/", "/app/%2fadmin.html%2f",
                 "/app/x%2f..%2fadmin.html%2f", "/app/./admin.html/", "/app/ADMIN.HTML", "/app/demo/fees.html"):
        r = client.get(path)
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"], path
        assert r.headers["x-frame-options"] == "DENY", path
    for path in ("/app/", "/app/index.html", "/app/?embed=1"):          # the chat page the widget frames
        r = client.get(path)
        assert r.status_code == 200 and "x-frame-options" not in r.headers, path
        assert f"frame-ancestors {config.FRAME_ANCESTORS}" in r.headers["content-security-policy"], path

    staff = client.get("/admin/me", headers=headers)
    assert staff.headers["cache-control"] == "no-store"
    assert "no-store" not in client.get("/health").headers.get("cache-control", "")
    assert client.get("/app/app.js").headers["cache-control"] == "no-cache"   # updated scripts reach browsers

    # The inline scripts were moved out, so the pages work under script-src 'self'.
    assert "<script>" not in page.text and "<script>" not in client.get("/app/admin.html").text


def test_streamed_answers_still_get_headers(client):
    r = client.post("/chat/stream", json={"message": "hello"})
    assert r.status_code == 200 and r.headers["x-content-type-options"] == "nosniff"
    assert json.loads(r.text.splitlines()[-1])["type"] == "done"


def test_hsts_only_over_https_and_report_only_switch(monkeypatch):
    with TestClient(app, base_url="https://testserver") as https:
        assert https.get("/health").headers["strict-transport-security"].startswith("max-age=63072000")
        monkeypatch.setattr(config, "CSP_REPORT_ONLY", True)
        r = https.get("/health")
        assert "content-security-policy-report-only" in r.headers
        assert "content-security-policy" not in r.headers


def test_cors_allows_only_listed_sites(client):
    def preflight(origin):
        return client.options("/chat", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                                "Access-Control-Request-Headers": "content-type"})
    ok = preflight("http://localhost:5500")
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5500"
    assert "access-control-allow-credentials" not in ok.headers
    assert "access-control-allow-origin" not in preflight("https://evil.example").headers
    assert "*" not in config.CORS_ORIGINS


def test_hidden_files_are_never_served(client, tmp_path):
    (tmp_path / ".env").write_text("SECRET=1")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]")
    (tmp_path / "page.html").write_text("<p>hi</p>")
    small = Starlette(routes=[Mount("/s", app=security.SafeStaticFiles(directory=tmp_path))])
    with TestClient(small) as c:
        assert c.get("/s/page.html").status_code == 200
        for path in ("/s/.env", "/s/.git/config", "/s/x/../.env"):
            assert c.get(path).status_code == 404, path
    assert client.get("/app/.DS_Store").status_code == 404


def test_api_docs_are_off_by_default(client):
    assert not config.API_DOCS
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def test_oversized_requests_are_refused(client, headers, monkeypatch):
    big = {"message": "hi", "language": "en", "padding": "x" * (config.MAX_JSON_KB * 1024)}
    r = client.post("/chat", json=big)
    assert r.status_code == 413 and r.headers["x-content-type-options"] == "nosniff"

    def pieces():                           # sent in chunks, with no Content-Length at all
        for _ in range(config.MAX_JSON_KB + 8):
            yield b" " * 1024
    assert client.post("/chat", content=pieces(), headers={"Content-Type": "application/json"}).status_code == 413

    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 1)
    upload = client.post("/admin/documents", headers=headers, data={"category": "campus"},
                         files={"file": ("big.txt", b"word " * 300_000, "text/plain")})
    assert upload.status_code == 413


def test_false_content_length_is_caught():
    """A client claims a small body but sends a big one: the byte count still stops it."""
    reached = []

    async def inner(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        reached.append(True)

    sent = []
    chunks = [{"type": "http.request", "body": b"x" * 1024, "more_body": True}] * (config.MAX_JSON_KB + 2)
    chunks = list(chunks) + [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive():
        return chunks.pop(0)

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/chat", "headers": [(b"content-length", b"10")]}
    asyncio.run(security.BodySizeLimit(inner)(scope, receive, send))
    assert not reached and sent[0]["status"] == 413


def test_input_size_limits(client):
    long = client.post("/chat", json={"message": "a" * 1500}).json()
    assert long["flag"] == "blocked"                     # still the friendly "shorten it" reply
    assert client.post("/chat", json={"message": "a" * (4 * config.MAX_MESSAGE_CHARS + 1)}).status_code == 422
    turns = [{"role": "user", "content": "hi"}] * (2 * config.MAX_HISTORY_TURNS + 1)
    assert client.post("/chat", json={"message": "hi", "history": turns}).status_code == 422
    turns = [{"role": "user", "content": "hi"}] * config.MAX_HISTORY_TURNS     # what the page sends
    assert client.post("/chat", json={"message": "hi", "history": turns}).status_code == 200
    assert client.post("/admin/login", json={"username": "u" * 51, "password": "x"}).status_code == 422
    assert client.post("/chat", json={"message": "hi", "category": "c" * 31}).status_code == 422


def test_upload_form_field_limits(client, headers):
    r = client.post("/admin/documents", headers=headers, data={"title": "t" * 201, "category": "campus"},
                    files={"file": ("a.txt", b"Some campus text that is long enough.", "text/plain")})
    assert r.status_code == 422


def test_sign_in_rate_limit(client, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_RATE_LIMIT_PER_MIN", 3)
    codes = [client.post("/admin/login", json={"username": f"nobody{i}", "password": "wrong-password"}).status_code
             for i in range(4)]
    assert codes == [401, 401, 401, 429]


def test_review_questions_are_rate_limited(client, headers, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", 1)
    ask = {"question": "When is the library open?"}
    assert client.post("/admin/reviews/ask", headers=headers, json=ask).status_code == 200
    assert client.post("/admin/reviews/ask", headers=headers, json=ask).status_code == 429


def test_rate_limit_tables_stay_small(monkeypatch):
    monkeypatch.setattr(config, "MAX_TRACKED_CLIENTS", 5)
    old = time.monotonic() - 120
    for i in range(20):
        main._recent[("chat", f"10.0.0.{i}")].append(old)
    main._forget_old_addresses(time.monotonic())
    assert len(main._recent) <= 5

    monkeypatch.setattr(auth, "_failed", {})
    auth._failed["victim"] = (0, time.time() + 300)          # an account that is locked right now
    for i in range(20):
        auth._failed[f"made-up-{i}"] = (1, 0.0)
    auth._forget_old_failures()
    assert len(auth._failed) <= 5 and "victim" in auth._failed   # the real lockout is kept


def test_failed_replace_keeps_old_version_and_removes_new_file(client, headers, monkeypatch):
    doc = client.post("/admin/documents", headers=headers, data={"title": "Library", "category": "campus"},
                      files={"file": ("library.txt", DOC_V1.encode(), "text/plain")}).json()
    before = set(config.UPLOAD_DIR.iterdir())

    def broken_reader(path):
        raise RuntimeError("parser crashed")
    monkeypatch.setattr(ingest, "extract_sections", broken_reader)
    r = client.put(f"/admin/documents/{doc['id']}", headers=headers,
                   files={"file": ("library2.txt", DOC_V2.encode(), "text/plain")})
    assert r.status_code == 422 and "could not be read" in r.json()["detail"]
    assert set(config.UPLOAD_DIR.iterdir()) == before          # the half-saved new file is gone
    monkeypatch.undo()

    def broken_embedder(texts):
        raise RuntimeError("embedding model crashed")
    monkeypatch.setattr(ingest.embeddings, "embed", broken_embedder)
    with pytest.raises(RuntimeError):
        service.replace_document(doc["id"], DOC_V2.encode(), "library2.txt", "sec-admin")
    assert set(config.UPLOAD_DIR.iterdir()) == before
    monkeypatch.undo()

    assert service.get_document(doc["id"])["version"] == 1      # students still see version 1
    client.delete(f"/admin/documents/{doc['id']}", headers=headers)


def test_launch_warnings(monkeypatch):
    text = " ".join(security.launch_warnings())
    assert "CORS_ORIGINS" in text and "FRAME_ANCESTORS" in text      # the defaults are for a laptop
    monkeypatch.setattr(config, "CORS_ORIGINS", ["*"])
    assert any("'*'" in w for w in security.launch_warnings())
    monkeypatch.setattr(config, "CORS_ORIGINS", ["https://www.nottingham.edu.my"])
    monkeypatch.setattr(config, "FRAME_ANCESTORS", "'self' https://*.nottingham.edu.my")
    assert security.launch_warnings() == []


def test_inline_styles_only_on_the_demo_pages():
    assert "'unsafe-inline'" in security.content_security_policy("/app/demo/fees.html")
    assert "'unsafe-inline'" in security.content_security_policy("/app/DEMO/FEES.HTML")
    for path in ("/app/demo/../admin.html", "/app/index.html", "/app/admin.html", "/demo/x.html"):
        assert "'unsafe-inline'" not in security.content_security_policy(path), path


def test_crash_reply_still_has_safety_headers():
    def boom(request):
        raise RuntimeError("crash")
    # Built like main.py: the framework's own error handler sits OUTSIDE the security middleware.
    crashing = Starlette(routes=[Route("/boom", boom)])
    crashing.add_middleware(security.SecurityHeaders)
    with TestClient(crashing, raise_server_exceptions=False) as c:
        r = c.get("/boom")
    assert r.status_code == 500 and r.json() == {"detail": "Internal server error"}
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


def test_huge_numbers_in_the_address_are_refused_not_crashing(client, headers):
    assert client.post("/feedback/99999999999999999999999/reason", json={"reason": "wrong"}).status_code == 422
    assert client.post("/feedback/0/reason", json={"reason": "wrong"}).status_code == 422
    assert client.post("/feedback/123456/reason", json={"reason": "wrong"}).status_code == 404
    for path in ("/admin/analytics?days=99999999999999999999", "/admin/reviews/summary?days=0"):
        assert client.get(path, headers=headers).status_code == 422, path
    assert client.get("/admin/analytics?days=7", headers=headers).status_code == 200


def test_full_rate_table_clears_a_tenth_at_once(monkeypatch):
    monkeypatch.setattr(config, "MAX_TRACKED_CLIENTS", 100)
    now = time.monotonic()
    for i in range(101):
        main._recent[("chat", f"10.1.0.{i}")].append(now - 50 + i * 0.4)    # all active in the last minute, oldest first
    main._forget_old_addresses(now)
    assert len(main._recent) == 90 and ("chat", "10.1.0.0") not in main._recent
    assert ("chat", "10.1.0.100") in main._recent
