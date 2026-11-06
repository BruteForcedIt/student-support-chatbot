"""Keyword search (BM25) over the stored chunks, used next to the meaning-based search.

The meaning search (embeddings) is good at "my room is damp" ~ "maintenance problems", but weak at
names and codes such as "Mabul" or "J2", which carry little meaning on their own. Keyword search is
the opposite. rag.retrieve() uses both, so a passage found by either one can reach the chat model.

BM25 is the standard keyword-ranking formula: a word scores higher when it is rare across the
knowledge base and appears in a short passage. The index is rebuilt from Chroma when the knowledge
base changes, so it never needs its own storage.
"""
import math
import re
import time
from collections import Counter

from . import vectorstore

# Very common words in English and Malay that say nothing about the topic.
STOPWORDS = set("""
a an and are as at be been but by can could did do does for from had has have how i if in into is it its
me my no not of on or our so than that the their them then there these they this to too up us was we
were what when where which who why will with would you your am im dont cant get got any some need want
know please help tell about just also should
saya awak anda kamu dia kami kita mereka yang dan atau di ke dari untuk dengan ini itu ada adalah apa
bagaimana mana bila boleh tidak tak nak mahu perlu sila tolong pada dalam juga akan sudah ialah
""".split())

_TOKEN = re.compile(r"[a-z0-9]+|[一-鿿]+")
_K1, _B = 1.5, 0.75          # the usual BM25 settings
_REFRESH_SECONDS = 60        # also re-read now and then, in case another process (CLI import) changed the KB

_index: dict | None = None


def tokens(text: str) -> list[str]:
    """Lower-case words, without stopwords; a trailing plural 's' is dropped ("tutors" -> "tutor").
    Chinese has no spaces, so it is split into overlapping two-character pieces ("宿舍费" -> 宿舍, 舍费)."""
    out = []
    for part in _TOKEN.findall(text.lower()):
        if "一" <= part[0] <= "鿿":
            out += [part[i:i + 2] for i in range(len(part) - 1)] or [part]
        elif part not in STOPWORDS and (len(part) > 1 or part.isdigit()):
            out.append(part[:-1] if len(part) > 4 and part.endswith("s") and not part.endswith("ss") else part)
    return out


def _build() -> dict:
    chunks = vectorstore.all_chunks()
    docs = [Counter(tokens(f"{c['title']}\n{c['text']}")) for c in chunks]
    df = Counter(word for d in docs for word in d)
    lengths = [sum(d.values()) for d in docs]
    return {"chunks": chunks, "docs": docs, "df": df, "lengths": lengths,
            "avg": (sum(lengths) / len(lengths)) if lengths else 1.0,
            "generation": vectorstore.generation(), "built": time.monotonic()}


def _get_index() -> dict:
    global _index
    if (_index is None or _index["generation"] != vectorstore.generation()
            or time.monotonic() - _index["built"] > _REFRESH_SECONDS):
        _index = _build()
    return _index


def search(query: str, k: int, category: str | None = None, max_share: float = 0.1) -> list[dict]:
    """Return up to k chunks that contain at least one *distinctive* query word, best first.

    A word is distinctive if it appears in no more than max_share of all chunks (or in at most 2),
    so "Mabul" counts but "room" or "student" do not. Each hit has the chunk fields plus "keyword_score"."""
    index = _get_index()
    n = len(index["chunks"])
    if n == 0:
        return []
    words = set(tokens(query))
    limit = max(2, int(n * max_share))
    rare = {w for w in words if 0 < index["df"][w] <= limit}
    if not rare:
        return []
    scored = []
    for chunk, doc, length in zip(index["chunks"], index["docs"], index["lengths"]):
        if category and chunk["category"] != category:
            continue
        if not rare & doc.keys():
            continue
        score = 0.0
        for w in words & doc.keys():
            idf = math.log(1 + (n - index["df"][w] + 0.5) / (index["df"][w] + 0.5))
            tf = doc[w]
            score += idf * tf * (_K1 + 1) / (tf + _K1 * (1 - _B + _B * length / index["avg"]))
        scored.append({**chunk, "keyword_score": round(score, 3)})
    scored.sort(key=lambda h: h["keyword_score"], reverse=True)
    return scored[:k]
