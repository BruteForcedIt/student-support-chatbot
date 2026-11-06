"""Talk to the chat model. LM Studio copies OpenAI's message format, so we use the openai library."""
import logging

from openai import OpenAI

from . import config

log = logging.getLogger("llm")
_client = None

EMPTY_REPLY_WARNING = ("The model reached its length limit without writing an answer (it was probably 'thinking'). "
                       "Keep LLM_REASONING_EFFORT=none, or turn thinking off for this model in LM Studio.")


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=120)
    return _client


def _extra() -> dict:
    """Settings sent with every request. reasoning_effort="none" switches off 'thinking' (see config.py)."""
    return {"reasoning_effort": config.LLM_REASONING_EFFORT} if config.LLM_REASONING_EFFORT else {}


def chat(messages: list[dict], model: str | None = None, temperature: float = 0.2, max_tokens: int = 700) -> str:
    response = client().chat.completions.create(
        model=model or config.LLM_MODEL, messages=messages, temperature=temperature, max_tokens=max_tokens,
        **_extra(),
    )
    choice = response.choices[0]
    text = choice.message.content or ""
    if not text.strip() and choice.finish_reason == "length":
        log.warning(EMPTY_REPLY_WARNING)
    return text


def stream(messages: list[dict], model: str | None = None, temperature: float = 0.2, max_tokens: int = 700):
    """Yield the reply piece by piece as the model writes it (LM Studio supports stream=true)."""
    response = client().chat.completions.create(
        model=model or config.LLM_MODEL, messages=messages, temperature=temperature,
        max_tokens=max_tokens, stream=True, **_extra(),
    )
    wrote, finish = False, None
    for chunk in response:
        if chunk.choices and chunk.choices[0].finish_reason:
            finish = chunk.choices[0].finish_reason
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            wrote = True
            yield chunk.choices[0].delta.content
    if not wrote and finish == "length":
        log.warning(EMPTY_REPLY_WARNING)


def check() -> str:
    """Return "" if the chat model can be used, otherwise a plain-English reason.
    Used before long jobs (the ethics tests) so they don't run for minutes and record only errors."""
    try:
        names = [m.id for m in client().with_options(timeout=5, max_retries=0).models.list()]
    except Exception:
        return f"The chat model is not reachable at {config.LLM_BASE_URL}. Check that LM Studio's server is running."
    if names and config.LLM_MODEL not in names:
        return (f"The model '{config.LLM_MODEL}' is not available on the model server. "
                f"Set LLM_MODEL to one of: {', '.join(names[:8])}.")
    return ""
