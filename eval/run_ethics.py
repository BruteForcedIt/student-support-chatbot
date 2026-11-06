"""Run the ethics tests from the command line and print a summary.

    python -m eval.run_ethics             # needs LM Studio running (the judge uses the chat model)
    python -m eval.run_ethics --no-judge  # rule-based checks only; answered refusals are marked "review"

The full report is saved to data/ethics/latest.json and shows in the admin page (Ethics tests tab),
where a person can also mark the "review" tests as passed or failed."""
import argparse
import sys

from backend import db, ethics, service


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-judge", action="store_true", help="don't ask the chat model to mark answers")
    args = parser.parse_args()
    db.init()
    try:
        report = ethics.run_suite(use_judge=not args.no_judge,
                                  progress=lambda d, t: print(f"\r  {d}/{t} tests", end="", flush=True))
    except service.ServiceError as exc:
        sys.exit(exc.message)
    print(f"\n\nPassed {report['passed']} of {report['total']} ({report['pass_rate']:.0%}) in {report['duration_s']}s\n")
    for cat, s in report["summary"].items():
        extra = "".join(f", {s[k]} {k}" for k in ("review", "error") if s[k])
        print(f"  {cat:<14} {s['pass']}/{s['total']} passed{extra}")
    failed = [c for c in report["cases"] if c["status"] in ("fail", "review", "error")]
    if failed:
        print("\nNeeds attention:")
        for c in failed:
            print(f"  [{c['status'].upper():6}] {c['id']} {c['prompt'][:60]!r}: {c['detail']}")
    ready = ethics.readiness(report)
    print(f"\nRelease check: {'READY' if ready['ready'] else 'NOT READY'}")
    for check in ready["checks"]:
        print(f"  [{'x' if check['ok'] else ' '}] {check['label']} ({check['detail']})")


if __name__ == "__main__":
    main()
