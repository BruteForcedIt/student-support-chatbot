"""Create a staff account:

    python -m backend.create_admin                    # Hub staff account (full access)
    python -m backend.create_admin --role reviewer    # lecturer account (Peer review only)

Hub staff can also add and remove accounts in the admin page (Staff accounts tab)."""
import argparse
import getpass
import sys

from . import auth, config, db


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--role", choices=list(config.ROLES), default="admin",
                        help="admin = Hub staff (everything), reviewer = lecturer (Peer review only)")
    args = parser.parse_args()
    db.init()
    username = input(f"New {config.ROLES[args.role]} username: ").strip()
    password = getpass.getpass(f"Password (at least {auth.MIN_PASSWORD} characters): ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    try:
        auth.create_user(username, password, args.role)
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{config.ROLES[args.role]} account '{username}' created. You can now sign in at /app/admin.html")


if __name__ == "__main__":
    main()
