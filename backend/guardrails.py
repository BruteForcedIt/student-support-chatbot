"""Safety checks that run BEFORE the question reaches the chat model.

Layer 1 (always on): distress words -> fixed message with human contacts, prompt-injection phrases -> polite refusal.
Layer 2 (optional): a safety model such as Llama Guard 3 1B in LM Studio. Set GUARD_MODEL to switch it on.

These are simple rules, not perfect. They will miss some things and occasionally flag harmless messages.
Agree the wording and contacts with the Hub staff, and test them (see eval/)."""
import logging
import re
from dataclasses import dataclass

from . import config

log = logging.getLogger("guardrails")

CRISIS_PATTERNS = [re.compile(p, re.I) for p in [
    r"\bsuicid", r"kill (myself|my self)", r"end (my|my own) life", r"end it all", r"want to die",
    r"don'?t want to (live|be alive)", r"self[- ]?harm", r"hurt myself", r"cut myself",
    r"better off without me", r"no reason to (live|go on|keep going)", r"(can'?t|cannot) go on living",
    r"tidak (mahu|mau|ingin) hidup", r"tak (nak|mahu|mau) hidup",
    r"bunuh diri", r"tamatkan (nyawa|hidup)", r"(nak|mahu|ingin) mati", r"mencederakan diri",
    r"自杀", r"不想活", r"想死", r"结束生命", r"伤害自己", r"自残",
]]

INJECTION_PATTERNS = [re.compile(p, re.I) for p in [
    r"ignore (all |any |the |your )?(previous|above|prior|earlier)? ?(instructions|prompts?|rules)",
    r"disregard (all |any |the |your )?(previous|above|prior)? ?(instructions|prompts?|rules)",
    r"(reveal|show|print|repeat) (me )?(your|the) (system )?(prompt|instructions)",
    r"you are now (?!a student)", r"developer mode", r"jailbreak", r"pretend (that )?you (have|are) no (rules|restrictions)",
    r"abaikan (semua |segala )?(arahan|peraturan)", r"忽略(之前|以上|所有)?的?(指令|指示|规则)",
]]

CRISIS_MESSAGE = {
    "en": ("I'm really sorry you're going through this, and I'm glad you said something. Please talk to a person "
           "right now. The 24/7 wellbeing hotline is {hotline}, or campus Security (24/7) on {security}. "
           "During office hours you can also reach Wellbeing and Learning Support on {phone} or {email}. "
           "If you are in immediate danger, call {emergency}."),
    "ms": ("Saya bersimpati dengan apa yang anda lalui, dan saya gembira anda berkongsi. Sila hubungi seseorang "
           "sekarang. Talian wellbeing 24 jam: {hotline}, atau Keselamatan kampus (24 jam): {security}. "
           "Pada waktu pejabat, hubungi Wellbeing and Learning Support di {phone} atau {email}. "
           "Jika anda dalam bahaya, sila hubungi {emergency}."),
    "zh": ("听到你正在经历这些，我很难过，也很高兴你说了出来。请现在就联系真人支持："
           "24小时心理支持热线 {hotline}，或校园保安（24小时）{security}。办公时间也可联系 Wellbeing and Learning Support，"
           "电话 {phone}，邮箱 {email}。如果你处于紧急危险中，请拨打 {emergency}。"),
}
BLOCKED_MESSAGE = {
    "en": "I can only help with student support questions. Please rephrase your question.",
    "ms": "Saya hanya boleh membantu dengan soalan sokongan pelajar. Sila tukar soalan anda.",
    "zh": "我只能回答与学生支持相关的问题。请换一种方式提问。",
}
TOO_LONG_MESSAGE = {
    "en": "That message is too long. Please keep it under {n} characters.",
    "ms": "Mesej terlalu panjang. Sila ringkaskan kepada kurang daripada {n} aksara.",
    "zh": "消息太长了，请控制在 {n} 个字符以内。",
}


@dataclass
class Verdict:
    action: str          # "ok" | "crisis" | "blocked"
    message: str = ""


def _text(table: dict, language: str, **kw) -> str:
    return table.get(language, table["en"]).format(**kw)


def _tel(number: str) -> str:
    """A tap-to-call link: '019-266 0691' -> 'tel:+60192660691' (Malaysian numbers), '999' -> 'tel:999'."""
    digits = re.sub(r"\D", "", number)
    if number.strip().startswith("+"):
        return "tel:+" + digits
    if digits.startswith("0") and len(digits) > 4:
        return "tel:+60" + digits[1:]
    return "tel:" + digits


def contacts() -> list[dict]:
    """The human contacts the chat page shows as tap-to-call buttons. The numbers come only from config.py,
    so the buttons always match the distress message."""
    return [{"key": key, "number": number, "tel": _tel(number)} for key, number in (
        ("hotline", config.WELLBEING_HOTLINE), ("security", config.SECURITY_HOTLINE),
        ("emergency", config.EMERGENCY_NUMBER))]


def check(text: str, language: str = "en") -> Verdict:
    if len(text) > config.MAX_MESSAGE_CHARS:
        return Verdict("blocked", _text(TOO_LONG_MESSAGE, language, n=config.MAX_MESSAGE_CHARS))

    if any(p.search(text) for p in CRISIS_PATTERNS):
        return Verdict("crisis", _text(CRISIS_MESSAGE, language, phone=config.WELLBEING_PHONE,
                                       email=config.WELLBEING_EMAIL, emergency=config.EMERGENCY_NUMBER,
                                       hotline=config.WELLBEING_HOTLINE, security=config.SECURITY_HOTLINE))

    if any(p.search(text) for p in INJECTION_PATTERNS):
        return Verdict("blocked", _text(BLOCKED_MESSAGE, language))

    if config.GUARD_MODEL:
        try:
            from . import llm

            # Llama Guard answers "safe" or "unsafe" + a category code. LM Studio applies its chat template.
            reply = llm.chat([{"role": "user", "content": text}], model=config.GUARD_MODEL,
                             temperature=0.0, max_tokens=20).strip().lower()
            if reply.startswith("unsafe"):
                log.info("guard model flagged a message: %s", reply.replace("\n", " "))
                return Verdict("blocked", _text(BLOCKED_MESSAGE, language))
        except Exception as exc:    # if the guard model is down, keep going with the rule-based checks
            log.warning("guard model unavailable: %s", exc)
    return Verdict("ok")
