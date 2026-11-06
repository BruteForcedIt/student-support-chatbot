"""One place that turns a student's message into a reply: safety checks first, then the RAG answer.
The /chat endpoints and the ethics tests both use this, so the tests check exactly what students get."""
from . import config, guardrails, rag


def clean_language(language: str) -> str:
    return language if language in config.LANGUAGES else "en"


def _stopped(verdict: guardrails.Verdict) -> dict:
    """The reply when a safety check stops the message before the model. Crisis replies carry the
    tap-to-call contacts, so the page's buttons always show the same numbers as the message."""
    result = {"reply": verdict.message, "sources": [], "answered": False, "flag": verdict.action,
              "top_score": 0.0, "retrieved_titles": []}
    if verdict.action == "crisis":
        result["contacts"] = guardrails.contacts()
    return result


def respond(message: str, language: str = "en", category: str = "general", history: list[dict] | None = None) -> dict:
    language = clean_language(language)
    verdict = guardrails.check(message, language)
    if verdict.action != "ok":
        return _stopped(verdict)
    return rag.answer(message, language, category, history or [])


def respond_stream(message: str, language: str = "en", category: str = "general", history: list[dict] | None = None):
    language = clean_language(language)
    verdict = guardrails.check(message, language)
    if verdict.action != "ok":
        yield {"type": "done", **_stopped(verdict)}
        return
    yield from rag.answer_stream(message, language, category, history or [])


def outcome(result: dict) -> str:
    """Short label used in the usage metrics."""
    if result.get("flag"):
        return result["flag"]             # small_talk | crisis | blocked
    return "answered" if result.get("answered") else "no_info"
