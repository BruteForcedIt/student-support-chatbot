"""Extra review tests for the security layer: path tricks, body-size edge cases, preflight, lockout pruning.
Raw ASGI calls are used so that the path reaches the server exactly as written (no client clean-up)."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from backend import auth, config, security
from backend.main import app


def call(path, method="GET", headers=None, chunks=None, scheme="http"):
    """Send one raw request through the whole app; return status, headers, body."""
    out = {"body": b""}
    parts = list(chunks) if chunks is not None else [b""]

    async def receive():
        if parts:
            b = parts.pop(0)
            return {"type": "http.request", "body": b, "more_body": bool(parts)}
        await asyncio.sleep(0)
        return {"type": "http.disconnect"}

    async def send(m):
        if m["type"] == "http.response.start":
            out["status"] = m["status"]
            out["headers"] = {k.decode(): v.decode() for k, v in m["headers"]}
        elif m["type"] == "http.response.body":
            out["body"] += m.get("body", b"")

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "path": path,
             "raw_path": path.encode(), "query_string": b"", "root_path": "", "scheme": scheme,
             "headers": headers or [], "client": ("9.9.9.9", 1), "server": ("x", 80)}
    asyncio.run(app(scope, receive, send))
    return out


@pytest.fixture(scope="module", autouse=True)
def started():
    with TestClient(app):
        yield


def denied_framing(r):
    return "frame-ancestors 'none'" in r["headers"]["content-security-policy"]


@pytest.mark.parametrize("path", ["/app/admin.html", "/app//admin.html", "/app/./admin.html",
                                  "/app/admin.html/", "/app/ADMIN.html", "/app/admin.HTML"])
def test_admin_page_never_framable_on_normal_paths(path):
    r = call(path)
    assert r["status"] == 200 and denied_framing(r) and r["headers"]["x-frame-options"] == "DENY"


def test_admin_page_uppercase_extension_not_framable():
    r = call("/app/ADMIN.HTML")
    if r["status"] != 200:
        pytest.skip("filesystem is case sensitive")
    assert denied_framing(r)


def test_admin_page_dot_segments_with_trailing_slash_not_framable():
    r = call("/app/./admin.html/")
    assert r["status"] == 200
    assert denied_framing(r)


@pytest.mark.parametrize("path", ["/app/.DS_Store", "/app/%2eDS_Store", "/app/demo/.x", "/app/.git/config",
                                  "/app/style\\.env", "/app//.env", "/app/vendor/../.env"])
def test_dotfiles_404(path):
    assert call(path)["status"] == 404


def test_body_limit_chunked_without_length():
    big = [b"x" * 40000, b"x" * 40000]
    r = call("/chat", "POST", headers=[(b"content-type", b"application/json")], chunks=big)
    assert r["status"] == 413
    assert "content-security-policy" in r["headers"]       # outer layer still adds headers to the 413


@pytest.mark.parametrize("value", [b" 999999999 ", b"-5", b"abc", b"1e9"])
def test_content_length_oddities_do_not_crash(value):
    r = call("/chat", "POST", headers=[(b"content-length", value), (b"content-type", b"application/json")],
             chunks=[b"{}"])
    assert r["status"] in (413, 422, 400)


def test_json_routes_do_not_get_upload_limit():
    for path in ("/chat", "/admin/login", "/admin/reviews", "/admin/ethics/run"):
        assert security.body_limit({"method": "POST", "path": path}) == config.MAX_JSON_KB * 1024
    assert security.body_limit({"method": "DELETE", "path": "/admin/documents/abc"}) == config.MAX_JSON_KB * 1024
    assert security.body_limit({"method": "POST", "path": "/admin/documents/"}) > 1024 * 1024


def test_preflight_has_cors_and_security_headers_and_is_not_blocked():
    r = call("/chat", "OPTIONS", headers=[(b"origin", b"http://localhost:5500"),
                                          (b"access-control-request-method", b"POST"),
                                          (b"access-control-request-headers", b"content-type")])
    assert r["status"] == 200
    assert r["headers"]["access-control-allow-origin"] == "http://localhost:5500"
    assert "x-content-type-options" in r["headers"]


def test_413_reply_carries_cors_header_for_allowed_origin():
    r = call("/chat", "POST", headers=[(b"origin", b"http://localhost:5500"), (b"content-length", b"9999999")])
    assert r["status"] == 413
    assert r["headers"].get("access-control-allow-origin") == "http://localhost:5500"


def test_hsts_not_faked_by_client_header():
    r = call("/health", headers=[(b"x-forwarded-proto", b"https")])
    assert "strict-transport-security" not in r["headers"]


def test_active_lock_survives_pruning(monkeypatch):
    monkeypatch.setattr(config, "MAX_TRACKED_CLIENTS", 3)
    import time
    auth._failed.clear()
    auth._failed["victim"] = (0, time.time() + 300)
    for i in range(10):
        auth._failed[f"u{i}"] = (1, 0.0)
        auth._forget_old_failures()
    assert "victim" in auth._failed and len(auth._failed) <= 4
    auth._failed.clear()
