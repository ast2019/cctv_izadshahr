#!/usr/bin/env python3
"""Synchronize .env.example with generated/required-env.txt.

This removes manual env-variable bookkeeping when cameras/sources are added.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
REQUIRED_ENV = ROOT / "generated" / "required-env.txt"

BEGIN = "# BEGIN AUTO-REQUIRED-ENV"
END = "# END AUTO-REQUIRED-ENV"
AUTO_HEADER = [
    "# -----------------------------------------------------------------------------",
    "# The block below is generated from inventory via scripts/render.py.",
    "# Update with: python3 scripts/sync-env-example.py --write",
    "# -----------------------------------------------------------------------------",
]


def parse_required_vars(path: pathlib.Path) -> list[str]:
    if not path.exists():
        sys.exit(
            "generated/required-env.txt not found. Run `python3 scripts/render.py` first."
        )

    variables: list[str] = []
    pattern = re.compile(r"^[A-Z0-9_]+$")
    for raw in path.read_text(encoding="utf-8").splitlines():
        var = raw.strip()
        if not var:
            continue
        if not pattern.match(var):
            sys.exit(f"Invalid env variable name in required-env.txt: {var!r}")
        variables.append(var)
    return variables


def upsert_auto_block(current: str, variables: list[str]) -> str:
    lines = current.splitlines()
    block = [BEGIN, *[f"{var}=" for var in variables], END]

    try:
        begin_idx = lines.index(BEGIN)
        end_idx = lines.index(END)
    except ValueError:
        merged = lines[:]
        if merged and merged[-1] != "":
            merged.append("")
        merged.extend(AUTO_HEADER)
        merged.extend(block)
        return "\n".join(merged) + "\n"

    if begin_idx > end_idx:
        sys.exit("Malformed .env.example: auto block markers are out of order.")

    merged = lines[:begin_idx] + block + lines[end_idx + 1 :]
    return "\n".join(merged) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync .env.example from generated/required-env.txt"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write updates to .env.example (default is check mode).",
    )
    args = parser.parse_args()

    required = parse_required_vars(REQUIRED_ENV)
    current = ENV_EXAMPLE.read_text(encoding="utf-8") if ENV_EXAMPLE.exists() else ""
    updated = upsert_auto_block(current, required)

    if current == updated:
        print(".env.example is up to date")
        return 0

    if args.write:
        ENV_EXAMPLE.write_text(updated, encoding="utf-8")
        print("Updated .env.example from generated/required-env.txt")
        return 0

    print(
        ".env.example is out of sync with generated/required-env.txt.\n"
        "Run: python3 scripts/sync-env-example.py --write"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
