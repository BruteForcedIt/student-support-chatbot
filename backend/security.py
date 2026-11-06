"""Web-security helpers used by main.py.

- SecurityHeaders: adds browser safety headers (which sites may frame a page, where scripts may load
  from, HTTPS-only, no caching of staff data) to every response.
- BodySizeLimit: refuses requests whose body is too big (413) before the server reads it all, so a
  huge upload or message cannot fill the memory or disk.
- SafeStaticFiles: serves the frontend/ folder but never hidden files such as .DS_Store or .env.
- launch_warnings(): reminders in the server log about settings that must change before a real launch.

Both middlewares are "pure ASGI": they only look at the start of each response and the incoming
bytes, so the word-by-word answers from /chat/stream still arrive as they are written.
"""
import json
import logging
import posixpath
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from . import config

log = logging.getLogger("security")

# The student chat page may be shown inside another site's page (the side-panel widget).
# Every other page and the API may never be framed, which stops "clickjacking" (a hidden frame
# tricking staff into clicking buttons).
_PERMISSIONS = "microphone=(self), camera=(), geolocation=(), payment=()"   # mic = voice input on the chat page
_HSTS = "max-age=63072000; includeSubDomains"   # 2 years; only sent over HTTPS


def _app_name(path: str) -> str | None:
    """The file a /app/... request points at, written one fixed way: lower case, "/" only, no "." or ".."
    parts, no slashes at either end. So "/app/ADMIN.HTML", "/app//admin.html/" and "/app/x/../admin.html"
    all become "admin.html" (some disks ignore upper/lower case). None if the path is not under /app."""
    clean = posixpath.normpath(path.replace("\\", "/").lower())
    if clean == "/app":
        return ""
    if not clean.startswith("/app/"):
        return None
    return clean[len("/app/"):].strip("/")


def _framable(path: str) -> bool:
    """True only for the student chat page itself, which the side-panel widget shows in a frame.
    An allow-list: every other page (admin page, demo pages, any odd spelling of a path) can never be
    framed. Frame rules only matter for pages, so the chat page's CSS/JS/images need no exception."""
    return _app_name(path) in ("", ".", "index.html")


def content_security_policy(path: str) -> str:
    """The Content-Security-Policy for one path: which sources the browser may load from.

    No inline scripts are allowed ('self' only), so injected <script> tags cannot run.
    The pages only call the API on the same server, so connect-src is 'self'. (The VS Code Live
    Server set-up serves the pages from port 5500, where these headers are not sent at all.)"""
    style = "'self' https://fonts.googleapis.com"
    name = _app_name(path)
    if name is not None and name.startswith("demo/"):
        # The demo pages stand in for a UNM web page: widget.js adds its own <style> block to the
        # page it is placed on, which a real host page's own policy must allow in the same way.
        style += " 'unsafe-inline'"
    frame_ancestors = config.FRAME_ANCESTORS if _framable(path) else "'none'"
    return "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        f"style-src {style}",
        "font-src https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        f"frame-ancestors {frame_ancestors}",
    ])


class SecurityHeaders:
    """Adds the safety headers to every HTTP response (without touching the body)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        is_https = scope.get("scheme") == "https"

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.setdefault("Permissions-Policy", _PERMISSIONS)
                csp_name = ("Content-Security-Policy-Report-Only" if config.CSP_REPORT_ONLY
                            else "Content-Security-Policy")
                headers.setdefault(csp_name, content_security_policy(path))
                if not _framable(path):
                    headers.setdefault("X-Frame-Options", "DENY")   # older browsers ignore frame-ancestors
                if is_https:
                    headers.setdefault("Strict-Transport-Security", _HSTS)
                if path.startswith("/admin/"):
                    headers["Cache-Control"] = "no-store"         # staff data must not be kept in caches
                elif path.startswith("/app/"):
                    headers.setdefault("Cache-Control", "no-cache")  # browser re-checks page files, so updates show at once
            await send(message)

        started = False

        async def send_tracked(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send_with_headers(message)

        try:
            await self.app(scope, receive, send_tracked)
        except Exception:
            # A crash before any reply: send a plain 500 that still carries the safety headers (the
            # server's own error page would not), then re-raise so the error is still logged.
            if not started:
                body = b'{"detail":"Internal server error"}'
                await send_with_headers({"type": "http.response.start", "status": 500,
                                         "headers": [(b"content-type", b"application/json"),
                                                     (b"content-length", str(len(body)).encode())]})
                await send_with_headers({"type": "http.response.body", "body": body})
            raise


class _TooLarge(Exception):
    pass


def body_limit(scope) -> int:
    """Largest request body in bytes for this request: documents may be up to MAX_UPLOAD_MB
    (plus 64 KB for the form's other fields); everything else is small JSON (MAX_JSON_KB)."""
    path = scope.get("path", "").rstrip("/")
    if scope.get("method") in ("POST", "PUT") and (path == "/admin/documents" or path.startswith("/admin/documents/")):
        return config.MAX_UPLOAD_MB * 1024 * 1024 + 64 * 1024
    return config.MAX_JSON_KB * 1024


class BodySizeLimit:
    """Refuses a request with 413 if its body is bigger than body_limit().

    Checks the Content-Length header first, then also counts the bytes as they arrive, because a
    client can send the body in pieces without a length or give a false length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = body_limit(scope)
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    too_big = int(value) > limit
                except ValueError:
                    too_big = False
                if too_big:
                    return await _send_413(send, limit)

        received = 0
        state = {"exceeded": False, "started": False}

        async def counting_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    state["exceeded"] = True
                    raise _TooLarge()
            return message

        async def guarded_send(message):
            if state["exceeded"]:
                return                      # the app's own error reply is replaced by the 413 below
            if message["type"] == "http.response.start":
                state["started"] = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            if not state["exceeded"]:
                raise
        if state["exceeded"] and not state["started"]:
            await _send_413(send, limit)


async def _send_413(send, limit: int) -> None:
    size = f"{limit // (1024 * 1024)} MB" if limit >= 1024 * 1024 else f"{limit // 1024} KB"
    body = json.dumps({"detail": f"The request is too large (limit about {size})."}).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


class SafeStaticFiles(StaticFiles):
    """StaticFiles that answers 404 for hidden files and folders (any part of the path that
    starts with "."), e.g. .DS_Store, .env or .git, so they can never be downloaded."""

    async def get_response(self, path: str, scope):
        if any(part.startswith(".") for part in path.replace("\\", "/").split("/") if part not in ("", ".")):
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)


def launch_warnings() -> list[str]:
    """Settings that are fine on a laptop but must be changed before students use the real site."""
    warnings = []
    origins = config.CORS_ORIGINS
    if "*" in origins:
        warnings.append("CORS_ORIGINS contains '*': any website can call the API. Set it to the real site address.")
    elif origins and all(_is_local(o) for o in origins):
        warnings.append("CORS_ORIGINS only lists localhost addresses. Add the real UNM site address before launch.")
    if "localhost" in config.FRAME_ANCESTORS or "127.0.0.1" in config.FRAME_ANCESTORS:
        warnings.append("FRAME_ANCESTORS still allows localhost pages to show the chat page. Remove them before launch.")
    if config.API_DOCS:
        warnings.append("API_DOCS is on: /docs lists every endpoint. Turn it off before launch.")
    return warnings


def _is_local(origin: str) -> bool:
    return urlsplit(origin).hostname in ("localhost", "127.0.0.1", "::1")

