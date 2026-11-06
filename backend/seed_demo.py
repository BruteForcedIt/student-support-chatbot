"""Fill the Analytics tab with SAMPLE usage data, for trying out or demonstrating the dashboard
before real students have used the Buddy.

    python -m backend.seed_demo            # adds about 30 days of sample questions and ratings
    python -m backend.seed_demo --clear    # removes ALL usage data and feedback (sample and real)

When presenting, say clearly that these numbers are sample data, not real usage."""
import argparse
import random
from datetime import datetime, timedelta, timezone

from . import config, db

WEIGHTS = {
    "category": {"general": 30, "academic": 25, "finance": 20, "campus": 12, "modules": 8, "documents": 5},
    "language": {"en": 70, "ms": 18, "zh": 12},
    "outcome": {"answered": 74, "no_info": 14, "small_talk": 8, "blocked": 2, "crisis": 1, "error": 1},
}
SAMPLE_GAPS = [
    ("campus", "Is there a shuttle bus to Kajang MRT on Sundays?"),
    ("general", "Can I bring a guest to the sports complex?"),
    ("finance", "Do I get a discount if my sibling also studies here?"),
    ("modules", "Can I audit a module from another school?"),
    ("documents", "How long does it take to get a replacement student card?"),
]


def pick(table: dict) -> str:
    return random.choices(list(table), weights=list(table.values()))[0]


def seed(days: int) -> None:
    db.init()
    now = datetime.now(timezone.utc)
    events, feedback = [], []
    for d in range(days, -1, -1):
        day = now - timedelta(days=d)
        weekday = day.weekday() < 5
        for _ in range(random.randint(25, 60) if weekday else random.randint(8, 20)):
            hour_myt = random.choices(range(24), weights=[1, 1, 0, 0, 0, 0, 1, 2, 4, 6, 7, 7, 6, 7, 8, 8, 7, 6, 5, 6, 7, 6, 4, 2])[0]
            ts = day.replace(hour=(hour_myt - 8) % 24, minute=random.randint(0, 59), second=0, microsecond=0)
            if ts > now:
                continue
            outcome, cat = pick(WEIGHTS["outcome"]), pick(WEIGHTS["category"])
            lang = pick(WEIGHTS["language"])
            latency = int(random.gauss(9000, 3000)) if outcome == "answered" else random.randint(150, 900)
            events.append((ts.isoformat(timespec="seconds"), lang, cat, outcome, max(latency, 1500 if outcome == "answered" else 100),
                           round(random.uniform(.4, .8), 3), "widget" if random.random() < .45 else "page"))
            if outcome in ("answered", "no_info") and random.random() < .3:
                up = random.random() < (.86 if outcome == "answered" else .25)
                reason = None if up else random.choice(["wrong", "incomplete", "incomplete", "unclear", "outdated"])
                feedback.append((ts.isoformat(timespec="seconds"), "up" if up else "down", lang, cat,
                                 int(outcome == "answered"), reason, "page"))
    with db.connect() as conn:
        conn.executemany("INSERT INTO chat_events(ts, language, category, outcome, latency_ms, top_score, channel) "
                         "VALUES (?,?,?,?,?,?,?)", events)
        conn.executemany("INSERT INTO feedback(ts, rating, language, category, answered, reason, channel) "
                         "VALUES (?,?,?,?,?,?,?)", feedback)
        if config.LOG_UNANSWERED:
            conn.executemany("INSERT INTO unanswered(ts, language, category, question) VALUES (?,?,?,?)",
                             [((now - timedelta(hours=7 * i)).isoformat(timespec="seconds"), "en", c, q)
                              for i, (c, q) in enumerate(SAMPLE_GAPS)])
    print(f"Added {len(events)} sample questions and {len(feedback)} sample ratings over {days} days.")


def clear() -> None:
    db.init()
    with db.connect() as conn:
        for table in ("chat_events", "feedback", "unanswered"):
            conn.execute(f"DELETE FROM {table}")
    print("Removed all usage data, ratings and unanswered questions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()
    clear() if args.clear else seed(args.days)
