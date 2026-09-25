"""
Set the web dashboard password.

    python -m web_dashboard.set_password            # prompts, writes DASHBOARD_PASSWORD_HASH to .env
    python -m web_dashboard.set_password --print    # prompts, prints the line instead (paste it yourself)

Only the salted hash is stored — never the password itself. Changing the
password logs out every existing dashboard session. Restart the dashboard
server afterwards so it picks up the new value.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from web_dashboard.auth import hash_password

MIN_LENGTH = 10
KEY = "DASHBOARD_PASSWORD_HASH"
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def _write_env(path: str, line: str) -> None:
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    replaced = False
    for i, existing in enumerate(lines):
        if existing.strip().startswith(f"{KEY}="):
            lines[i] = line
            replaced = True
    if not replaced:
        lines += ["", "# ── Web dashboard login (hash only — set via: python -m web_dashboard.set_password)", line]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--print", action="store_true", help="print the .env line instead of writing it")
    parser.add_argument("--env-file", default=ENV_PATH, help="env file to update (default: project .env)")
    args = parser.parse_args()

    password = getpass.getpass("New dashboard password: ")
    if len(password) < MIN_LENGTH:
        print(f"Password must be at least {MIN_LENGTH} characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Repeat password: ") != password:
        print("Passwords do not match.", file=sys.stderr)
        return 1

    line = f"{KEY}={hash_password(password)}"
    if args.print:
        print(line)
    else:
        _write_env(args.env_file, line)
        print(f"Saved {KEY} to {args.env_file}. Restart the dashboard server to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
