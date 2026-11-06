"""The web server. Run:  uvicorn backend.main:app --port 8000

Security layers (headers, body-size limit, hidden-file blocking) live in security.py."""
import heapq
import json
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Path, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import assistant, auth, config, db, embeddings, ethics, guardrails, insights, security, service

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    for warning in security.launch_warnings():   # reminders for staff, not errors
        log.warning("Before launch: %s", warning)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    embeddings.embed(["warm up"])          # load the embedding model now, not on the first student's question
    if service.stats()["needs_reindex"]:
        log.warning("The embedding model changed since documents were uploaded. "
                    "Use 'Rebuild search index' (Maintenance) in the admin page.")
    yield


# The automatic API pages (/docs, /redoc, /openapi.json) are off unless API_DOCS=true.
app = FastAPI(title="Student Support Chat Buddy", lifespan=lifespan,
              docs_url="/docs" if config.API_DOCS else None,
              redoc_url="/redoc" if config.API_DOCS else None,
              openapi_url="/openapi.json" if config.API_DOCS else None)
# Order matters: the last one added runs first. Security headers wrap everything (so even a 413 or
# 429 reply gets them), then CORS, then the body-size limit, then the routes.
app.add_middleware(security.BodySizeLimit)
# CORS: which other websites' pages may call this API from a browser (CORS_ORIGINS in config.py).
# Staff sign in with an "Authorization: Bearer" header, not cookies, so credentials stay off.
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])
app.add_middleware(security.SecurityHeaders)


@app.exception_handler(service.ServiceError)
async def service_error_handler(_, exc: service.ServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


# ------------------------------------------------------------------ rate limits
# (kind of request, address) -> times of that address's requests in the last minute
_recent: dict[tuple[str, str], deque] = defaultdict(deque)
_recent_lock = threading.Lock()


def _forget_old_addresses(now: float) -> None:
    """Keep the table small. Only runs when the table is full: drops addresses with nothing in the last
    minute, and if it is still over 90% full (e.g. a flood from many addresses), the 10% that were quiet
    longest. Clearing 10% at once means this slower clean-up runs rarely, not on every request."""
    cap = config.MAX_TRACKED_CLIENTS
    if len(_recent) <= cap:
        return
    for key in [k for k, q in _recent.items() if not q or now - q[-1] > 60]:
        del _recent[key]
    target = int(cap * 0.9)
    if len(_recent) > target:
        for key in heapq.nsmallest(len(_recent) - target, _recent, key=lambda k: _recent[k][-1]):
            del _recent[key]


def _check_rate(request: Request, kind: str, limit: int, message: str) -> None:
    if limit <= 0:
        return
    key = (kind, request.client.host if request.client else "unknown")
    now = time.monotonic()
    with _recent_lock:
        q = _recent[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, message)
        q.append(now)
        _forget_old_addresses(now)


def rate_limit(request: Request) -> None:
    """At most RATE_LIMIT_PER_MIN chat messages per minute from one address. Stops one person
    (or a script) from tying up the model for everyone."""
    _check_rate(request, "chat", config.RATE_LIMIT_PER_MIN,
                "You're sending messages very quickly. Please wait a minute and try again.")


def login_rate_limit(request: Request) -> None:
    """At most LOGIN_RATE_LIMIT_PER_MIN sign-in attempts per minute from one address, on top of the
    per-username lockout in auth.py. Slows down password guessing across many usernames."""
    _check_rate(request, "login", config.LOGIN_RATE_LIMIT_PER_MIN,
                "Too many sign-in attempts from this device. Please wait a minute and try again.")


def review_rate_limit(request: Request) -> None:
    """Staff test questions use the chat model too, so they share the chat limit (counted separately)."""
    _check_rate(request, "review", config.RATE_LIMIT_PER_MIN,
                "You're asking questions very quickly. Please wait a minute and try again.")


# ------------------------------------------------------------------ students


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


# Size limits on what the browser may send. The message limit is well above MAX_MESSAGE_CHARS on purpose:
# a normal long message still gets the friendly "please shorten it" reply in the student's language
# (guardrails.py); only absurd sizes are refused outright.
class ChatIn(BaseModel):
    message: str = Field(max_length=4 * config.MAX_MESSAGE_CHARS)
    language: str = Field(default="en", max_length=10)
    category: str = Field(default="general", max_length=30)
    history: list[Turn] = Field(default=[], max_length=2 * config.MAX_HISTORY_TURNS)
    channel: Literal["page", "widget"] = "page"


def _inputs(body: ChatIn):
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Please type a question.")
    history = [t.model_dump() for t in body.history][-config.MAX_HISTORY_TURNS:]
    return message, assistant.clean_language(body.language), history


def _record(result: dict, body: ChatIn, message: str, language: str, started: float) -> None:
    try:
        insights.record_event(result, assistant.outcome(result), language, body.category,
                              (time.perf_counter() - started) * 1000, body.channel, message)
    except Exception:          # metrics must never break a student's answer
        log.exception("could not record chat event")


@app.post("/chat", dependencies=[Depends(rate_limit)])
def chat(body: ChatIn):
    message, language, history = _inputs(body)
    started = time.perf_counter()
    try:
        result = assistant.respond(message, language, body.category, history)
    except Exception:
        log.exception("chat failed")
        _record({"flag": "error"}, body, "", language, started)
        raise HTTPException(503, "The AI model is not reachable. Check that LM Studio's server is running.")
    _record(result, body, message, language, started)
    return result


@app.post("/chat/stream", dependencies=[Depends(rate_limit)])
def chat_stream(body: ChatIn):
    """Same as /chat, but the reply arrives word by word as newline-separated JSON events
    (status, delta..., done). The page shows text as soon as the model starts writing."""
    message, language, history = _inputs(body)
    started = time.perf_counter()

    def events():
        try:
            for event in assistant.respond_stream(message, language, body.category, history):
                if event["type"] == "done":
                    _record(event, body, message, language, started)
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception:
            log.exception("chat stream failed")
            _record({"flag": "error"}, body, "", language, started)
            yield json.dumps({"type": "error", "detail": "The AI model is not reachable. "
                              "Check that LM Studio's server is running."}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class FeedbackIn(BaseModel):
    rating: Literal["up", "down"]
    language: str = Field(default="en", max_length=10)
    category: str = Field(default="general", max_length=30)
    answered: bool = True
    channel: Literal["page", "widget"] = "page"


@app.post("/feedback", dependencies=[Depends(rate_limit)])
def feedback(body: FeedbackIn):
    """Thumbs up/down on an answer. Only the rating and its context are stored, never the message text."""
    fid = insights.add_feedback(body.rating, body.language, body.category, body.answered, body.channel)
    return {"ok": True, "id": fid}


class ReasonIn(BaseModel):
    reason: Literal["wrong", "incomplete", "unclear", "outdated"]


@app.post("/feedback/{feedback_id}/reason", dependencies=[Depends(rate_limit)])
def feedback_reason(body: ReasonIn, feedback_id: int = Path(ge=1, le=2**63 - 1)):   # SQLite's largest number
    """After a thumbs-down, the student can say what was wrong (one tap, a fixed list, no free text)."""
    if not insights.set_feedback_reason(feedback_id, body.reason):
        raise HTTPException(404, "Feedback not found.")
    return {"ok": True}


@app.get("/contacts")
def contacts():
    """The 24/7 numbers the chat page shows (sidebar, Help, distress card), from config.py."""
    return {"contacts": guardrails.contacts()}


@app.get("/health")
def health():
    return {"ok": True}


# ------------------------------------------------------- staff: sign in, accounts
# Hub staff ("admin" accounts) can use everything. Lecturers ("reviewer" accounts) can only use
# Peer review: those endpoints use auth.current_account / current_user, all others auth.require_admin.
class LoginIn(BaseModel):
    username: str = Field(max_length=50)
    password: str = Field(max_length=200)


@app.post("/admin/login", dependencies=[Depends(login_rate_limit)])
def admin_login(body: LoginIn):
    account = auth.login(body.username, body.password)
    db.audit(account["username"], "login")
    return account


@app.post("/admin/logout")
def admin_logout(authorization: str | None = Header(default=None), user: str = Depends(auth.current_user)):
    auth.logout(authorization[7:].strip())   # current_user already checked the header is valid
    return {"ok": True}


@app.get("/admin/me")
def admin_me(account: dict = Depends(auth.current_account)):
    return {**account, "role_label": config.ROLES.get(account["role"], account["role"])}


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


@app.post("/admin/me/password")
def change_password(body: PasswordIn, authorization: str | None = Header(default=None),
                    user: str = Depends(auth.current_user)):
    auth.change_password(user, body.current_password, body.new_password, keep_token=authorization[7:].strip())
    db.audit(user, "password")
    return {"ok": True}


@app.get("/admin/users")
def list_users(user: str = Depends(auth.require_admin)):
    return {"users": service.list_users(), "roles": config.ROLES}


class UserIn(BaseModel):
    username: str = Field(max_length=50)
    password: str = Field(max_length=200)
    role: Literal["admin", "reviewer"] = "reviewer"


@app.post("/admin/users")
def add_user(body: UserIn, user: str = Depends(auth.require_admin)):
    return service.add_user(body.username, body.password, body.role, user)


@app.delete("/admin/users/{username}")
def remove_user(username: str, user: str = Depends(auth.require_admin)):
    service.remove_user(username, user)
    return {"ok": True}


# ------------------------------------------------------ Hub staff: knowledge base
@app.get("/admin/documents")
def list_documents(user: str = Depends(auth.require_admin)):
    return [service.public(d) for d in service.list_documents()]


@app.post("/admin/documents")
def upload_document(
    file: UploadFile = File(...),
    title: str = Form("", max_length=200),
    category: str = Form("general", max_length=30),
    source_url: str = Form("", max_length=500),
    user: str = Depends(auth.require_admin),
):
    data = file.file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    return service.add_document(data, file.filename or "upload", title, category, source_url, user)


@app.put("/admin/documents/{doc_id}")
def replace_document(
    doc_id: str,
    file: UploadFile = File(...),
    title: str = Form("", max_length=200),
    category: str = Form("", max_length=30),
    source_url: str | None = Form(None, max_length=500),
    user: str = Depends(auth.require_admin),
):
    data = file.file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    return service.replace_document(doc_id, data, file.filename or "upload", user,
                                    title or None, category or None, source_url)


@app.delete("/admin/documents/{doc_id}")
def delete_document(doc_id: str, user: str = Depends(auth.require_admin)):
    service.delete_document(doc_id, user)
    return {"ok": True}


@app.get("/admin/stats")
def admin_stats(user: str = Depends(auth.require_admin)):
    return service.stats()


@app.post("/admin/reindex")
def admin_reindex(user: str = Depends(auth.require_admin)):
    return service.reindex_all(user)


@app.get("/admin/audit")
def admin_audit(user: str = Depends(auth.require_admin)):
    with db.connect() as conn:
        rows = conn.execute("SELECT ts, username, action, doc_id, detail FROM audit_log ORDER BY id DESC LIMIT 50").fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------- analytics and peer review
@app.get("/admin/analytics")
def admin_analytics(days: int = Query(30, ge=1, le=365), user: str = Depends(auth.require_admin)):
    return insights.analytics(days)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=config.MAX_MESSAGE_CHARS)
    language: str = Field(default="en", max_length=10)
    category: str = Field(default="general", max_length=30)


@app.post("/admin/reviews/ask", dependencies=[Depends(review_rate_limit)])
def review_ask(body: AskIn, user: str = Depends(auth.current_user)):
    """Staff and lecturers ask the bot a test question to review. Not counted in student usage metrics."""
    try:
        return assistant.respond(body.question.strip(), body.language, body.category, [])
    except Exception:
        log.exception("review ask failed")
        raise HTTPException(503, "The AI model is not reachable. Check that LM Studio's server is running.")


class ReviewIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=6000)
    language: str = Field(default="en", max_length=10)
    accuracy: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    tone: int = Field(ge=1, le=5)
    safe: bool
    comment: str = Field(default="", max_length=1000)


@app.post("/admin/reviews")
def review_add(body: ReviewIn, account: dict = Depends(auth.current_account)):
    rid = insights.add_review(account["username"], body.model_dump(), account["role"])
    db.audit(account["username"], "review", None,
             f"rated an answer {body.accuracy}/{body.completeness}/{body.clarity}/{body.tone}")
    return {"ok": True, "id": rid}


@app.get("/admin/reviews")
def review_list(account: dict = Depends(auth.current_account)):
    """Hub staff see every review; a lecturer sees only their own, so they review independently."""
    return insights.recent_reviews(reviewer=None if account["role"] == "admin" else account["username"])


@app.get("/admin/reviews/summary")
def review_summary(days: int = Query(90, ge=1, le=365), user: str = Depends(auth.current_user)):
    return insights.review_summary(days)


# ------------------------------------------------------------ ethics tests
@app.get("/admin/ethics")
def ethics_report(user: str = Depends(auth.require_admin)):
    latest = ethics.latest()
    return {"status": ethics.status(), "latest": latest, "history": ethics.history(),
            "readiness": ethics.readiness(latest), "categories": ethics.CATEGORY_INFO}


class EthicsRunIn(BaseModel):
    judge: bool = True


@app.post("/admin/ethics/run")
def ethics_run(body: EthicsRunIn, user: str = Depends(auth.require_admin)):
    if not ethics.start_background(user, body.judge):     # 503 if the chat model is not reachable
        raise HTTPException(409, "The ethics tests are already running.")
    db.audit(user, "ethics", None, "started the ethics tests")
    return ethics.status()


class VerdictIn(BaseModel):
    status: Literal["pass", "fail"]


@app.post("/admin/ethics/cases/{case_id}/verdict")
def ethics_verdict(case_id: str, body: VerdictIn, user: str = Depends(auth.require_admin)):
    """A person read a reply the judge could not decide and marks it passed or failed."""
    report = ethics.mark_case(case_id, body.status, user)
    db.audit(user, "ethics_check", None, f"marked {case_id} as {'passed' if body.status == 'pass' else 'failed'}")
    return {"latest": report, "readiness": ethics.readiness(report)}


# Serves the admin page at http://localhost:8000/app/admin.html (hidden files such as .DS_Store are never served)
if config.FRONTEND_DIR.exists():
    app.mount("/app", security.SafeStaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
