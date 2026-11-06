"""Measure how well the chatbot does on your question list.

    python -m eval.run_eval                  (from the project folder, with LM Studio's server running)
    python -m eval.run_eval --retrieval-only (skips the chat model: only tests the document search)

Edit eval/questions.csv. Columns:
  question, language (en/ms/zh), category, answerable (yes/no),
  expected_title (the document that should be found; if several documents answer it, list them separated by |),
  expected_keywords (words the answer must contain, separated by |)
"""
import argparse
import csv
from pathlib import Path

from backend import db, guardrails, rag

HERE = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--file", default=str(HERE / "questions.csv"))
    args = parser.parse_args()
    db.init()

    rows = list(csv.DictReader(open(args.file, encoding="utf-8")))
    results, yes_scores, no_scores = [], [], []
    for row in rows:
        question, lang, cat = row["question"], row.get("language") or "en", row.get("category") or "general"
        answerable = row["answerable"].strip().lower() == "yes"
        flag = guardrails.check(question, lang)
        out = {"question": question, "language": lang, "answerable": row["answerable"], "retrieval_ok": "",
               "answer_ok": "", "top_score": "", "reply": ""}

        if flag.action != "ok":
            out.update(reply=f"[guardrail:{flag.action}] {flag.message}", answer_ok="n/a")
        else:
            # Same search as the live chat (including the reworded second search when --retrieval-only is off)
            hits, top = (rag.retrieve(question, cat) if args.retrieval_only else rag.find_passages(question, cat, []))
            out["top_score"] = round(top, 3)
            (yes_scores if answerable else no_scores).append(top)
            titles = [h["title"].lower() for h in hits]
            if answerable:
                expected = {t.strip().lower() for t in row["expected_title"].split("|") if t.strip()}
                out["retrieval_ok"] = "PASS" if expected & set(titles) else "FAIL"
            else:
                # Passages may still reach the model (keyword matches, reworded search): the model then
                # has to say it doesn't know, which the answer check below tests.
                out["retrieval_ok"] = "n/a"

            if not args.retrieval_only:
                result = rag.answer(question, lang, cat)
                out["reply"] = result["reply"]
                if answerable:
                    keywords = [k.strip().lower() for k in row["expected_keywords"].split("|") if k.strip()]
                    ok = result["answered"] and all(k in result["reply"].lower() for k in keywords)
                else:
                    ok = not result["answered"]
                out["answer_ok"] = "PASS" if ok else "FAIL"
        results.append(out)

    with open(HERE / "results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    def rate(key, language=None):
        scored = [r[key] for r in results if r[key] in ("PASS", "FAIL") and language in (None, r["language"])]
        return f"{scored.count('PASS')}/{len(scored)}" if scored else "n/a"

    languages = sorted({r["language"] for r in results})

    def by_language(key):
        return "   (" + ", ".join(f"{lang} {rate(key, lang)}" for lang in languages) + ")"

    print(f"\nQuestions: {len(results)}")
    print(f"Document search correct : {rate('retrieval_ok')}{by_language('retrieval_ok')}")
    if not args.retrieval_only:
        print(f"Final answer correct    : {rate('answer_ok')}{by_language('answer_ok')}")
    if yes_scores and no_scores:
        low_yes, high_no = min(yes_scores), max(no_scores)
        print(f"\nLowest score for answerable questions : {low_yes:.2f}")
        print(f"Highest score for unanswerable ones   : {high_no:.2f}")
        if low_yes > high_no:
            print(f"-> Clean gap. MIN_SCORE could be about {(low_yes + high_no) / 2:.2f}")
        else:
            print("-> The scores overlap. That is expected with casual questions: keyword matches and the model's "
                  "own \"I don't know\" decide those. Check 'Final answer correct' for unanswerable questions.")
    print("Details saved to eval/results.csv")


if __name__ == "__main__":
    main()
