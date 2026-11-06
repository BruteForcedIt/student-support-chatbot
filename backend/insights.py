"""Usage metrics, peer assessment (student ratings + staff reviews) and the numbers behind the admin dashboard.

Privacy: chat_events stores only labels and timings, never what the student typed.
The one exception is the optional "unanswered questions" list (LOG_UNANSWERED, off by default)."""
from datetime import datetime, timedelta, timezone

from . import config, db

OUTCOMES = ["answered", "no_info", "small_talk", "crisis", "blocked", "error"]
FEEDBACK_REASONS = {
    "wrong": "Wrong or misleading",
    "incomplete": "Didn't answer my question",
    "unclear": "Hard to understand",
    "outdated": "Out of date",
}
RUBRIC = ["accuracy", "completeness", "clarity", "tone"]


def _clean(value: str, allowed, default: str) -> str:
    return value if value in allowed else default


def record_event(result: dict, outcome: str, language: str, category: str, latency_ms: int,
                 channel: str = "page", question: str = "") -> None:
    language = _clean(language, config.LANGUAGES, "en")
    category = _clean(category, config.CATEGORIES, "general")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO chat_events(ts, language, category, outcome, latency_ms, top_score, channel) "
            "VALUES (?,?,?,?,?,?,?)",
            (db.now_iso(), language, category, outcome, int(latency_ms), float(result.get("top_score") or 0),
             _clean(channel, ("page", "widget"), "page")),
        )
        # Only questions the bot could not answer, never crisis or blocked messages, and only if switched on.
        if config.LOG_UNANSWERED and outcome == "no_info" and question:
            conn.execute("INSERT INTO unanswered(ts, language, category, question) VALUES (?,?,?,?)",
                         (db.now_iso(), language, category, question[:300]))


def add_feedback(rating: str, language: str, category: str, answered: bool, channel: str = "page") -> int:
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO feedback(ts, rating, language, category, answered, channel) VALUES (?,?,?,?,?,?)",
            (db.now_iso(), rating, _clean(language, config.LANGUAGES, "en"),
             _clean(category, config.CATEGORIES, "general"), int(answered),
             _clean(channel, ("page", "widget"), "page")),
        )
        return cur.lastrowid


def set_feedback_reason(feedback_id: int, reason: str) -> bool:
    """A reason can be added once, only to a thumbs-down."""
    with db.connect() as conn:
        cur = conn.execute("UPDATE feedback SET reason=? WHERE id=? AND rating='down' AND reason IS NULL",
                           (reason, feedback_id))
        return cur.rowcount == 1


def add_review(reviewer: str, data: dict, role: str = "admin") -> int:
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO staff_reviews(ts, reviewer, question, answer, language, accuracy, completeness, clarity, "
            "tone, safe, comment, reviewer_role) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (db.now_iso(), reviewer, data["question"], data["answer"], _clean(data["language"], config.LANGUAGES, "en"),
             data["accuracy"], data["completeness"], data["clarity"], data["tone"], int(data["safe"]),
             data.get("comment", ""), _clean(role, config.ROLES, "admin")),
        )
        return cur.lastrowid


def recent_reviews(limit: int = 20, reviewer: str | None = None) -> list[dict]:
    """Newest reviews first. With `reviewer`, only that person's (lecturers see only their own,
    so other people's scores don't sway theirs)."""
    with db.connect() as conn:
        if reviewer:
            rows = conn.execute("SELECT * FROM staff_reviews WHERE reviewer=? ORDER BY id DESC LIMIT ?",
                                (reviewer, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM staff_reviews ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def _review_averages(row) -> dict | None:
    """(count, avg accuracy, completeness, clarity, tone, safe) -> the numbers the page shows."""
    if not row or not row[0]:
        return None
    return {"count": row[0], **{k: round(row[i + 1], 2) for i, k in enumerate(RUBRIC)}, "safe_rate": round(row[5], 3)}


REVIEW_AVERAGES_SQL = ("SELECT COUNT(*), AVG(accuracy), AVG(completeness), AVG(clarity), AVG(tone), AVG(safe) "
                       "FROM staff_reviews WHERE ts>=?")


def review_summary(days: int = 90) -> dict:
    """Peer assessment side by side: students' thumbs up/down and reasons, and staff rubric scores,
    split into lecturers and Hub staff. Collected separately, so each group's view is independent."""
    days = max(1, min(days, 365))
    since = _since(days)
    with db.connect() as conn:
        up, down = conn.execute("SELECT SUM(rating='up'), SUM(rating='down') FROM feedback WHERE ts>=?",
                                (since,)).fetchone()
        reasons = dict(conn.execute("SELECT reason, COUNT(*) FROM feedback WHERE ts>=? AND reason IS NOT NULL "
                                    "GROUP BY 1", (since,)).fetchall())
        overall = conn.execute(REVIEW_AVERAGES_SQL, (since,)).fetchone()
        by_role = {role: _review_averages(conn.execute(REVIEW_AVERAGES_SQL + " AND reviewer_role=?",
                                                       (since, role)).fetchone()) for role in config.ROLES}
    up, down = up or 0, down or 0
    return {
        "days": days,
        "students": {"ratings": up + down, "helpful_rate": round(up / (up + down), 3) if up + down else None,
                     "reasons": {k: reasons.get(k, 0) for k in FEEDBACK_REASONS}, "reason_labels": FEEDBACK_REASONS},
        "staff": _review_averages(overall),
        "staff_by_role": by_role,
        "role_labels": config.ROLES,
    }


def analytics(days: int = 30) -> dict:
    """Everything the Analytics tab draws, for the last `days` days."""
    days = max(1, min(days, 365))
    since = _since(days)
    with db.connect() as conn:
        q = lambda sql, *a: conn.execute(sql, (since, *a)).fetchall()   # noqa: E731

        per_day = {r[0]: {"total": r[1], "answered": r[2]} for r in q(
            "SELECT substr(ts,1,10), COUNT(*), SUM(outcome='answered') FROM chat_events WHERE ts>=? GROUP BY 1")}
        outcomes = dict(q("SELECT outcome, COUNT(*) FROM chat_events WHERE ts>=? GROUP BY 1"))
        languages = dict(q("SELECT language, COUNT(*) FROM chat_events WHERE ts>=? GROUP BY 1"))
        channels = dict(q("SELECT channel, COUNT(*) FROM chat_events WHERE ts>=? GROUP BY 1"))
        by_category = {r[0]: {"total": r[1], "answered": r[2] or 0, "no_info": r[3] or 0} for r in q(
            "SELECT category, COUNT(*), SUM(outcome='answered'), SUM(outcome='no_info') "
            "FROM chat_events WHERE ts>=? GROUP BY 1")}
        latencies = [r[0] for r in q(
            "SELECT latency_ms FROM chat_events WHERE ts>=? AND outcome='answered' ORDER BY latency_ms")]
        hours = dict(q("SELECT CAST(substr(ts,12,2) AS INTEGER), COUNT(*) FROM chat_events WHERE ts>=? GROUP BY 1"))

        fb = {r[0]: {"up": r[1] or 0, "down": r[2] or 0} for r in q(
            "SELECT category, SUM(rating='up'), SUM(rating='down') FROM feedback WHERE ts>=? GROUP BY 1")}
        reasons = dict(q("SELECT reason, COUNT(*) FROM feedback WHERE ts>=? AND reason IS NOT NULL GROUP BY 1"))

        review_row = conn.execute(REVIEW_AVERAGES_SQL, (since,)).fetchone()
        unanswered = [dict(r) for r in conn.execute(
            "SELECT ts, language, category, question FROM unanswered WHERE ts>=? ORDER BY id DESC LIMIT 25",
            (since,)).fetchall()]

    # Fill in days with no questions so the line chart has no gaps.
    today = datetime.now(timezone.utc).date()
    series = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        series.append({"date": d, **per_day.get(d, {"total": 0, "answered": 0})})

    total = sum(outcomes.values())
    up = sum(v["up"] for v in fb.values())
    down = sum(v["down"] for v in fb.values())

    def pct(p):
        return latencies[min(len(latencies) - 1, int(p * len(latencies)))] if latencies else None

    reviews = _review_averages(review_row)

    # Local time (Malaysia is UTC+8) for the busy-hours chart.
    offset = 8
    busy = [0] * 24
    for h, n in hours.items():
        busy[(h + offset) % 24] += n

    return {
        "days": days,
        "totals": {
            "questions": total,
            "answered": outcomes.get("answered", 0),
            "answer_rate": round(outcomes.get("answered", 0) / total, 3) if total else None,
            "helpful_rate": round(up / (up + down), 3) if up + down else None,
            "ratings": up + down,
            "median_ms": pct(0.5),
            "p90_ms": pct(0.9),
            "crisis": outcomes.get("crisis", 0),
        },
        "per_day": series,
        "outcomes": {k: outcomes.get(k, 0) for k in OUTCOMES},
        "languages": {k: languages.get(k, 0) for k in config.LANGUAGES},
        "channels": channels,
        "categories": [{"category": c, **by_category.get(c, {"total": 0, "answered": 0, "no_info": 0}),
                        **fb.get(c, {"up": 0, "down": 0})} for c in config.CATEGORIES],
        "busy_hours": busy,
        "feedback_reasons": {k: reasons.get(k, 0) for k in FEEDBACK_REASONS},
        "reason_labels": FEEDBACK_REASONS,
        "staff_reviews": reviews,
        "unanswered_enabled": config.LOG_UNANSWERED,
        "unanswered": unanswered,
    }
