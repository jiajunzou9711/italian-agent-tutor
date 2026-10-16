#!/usr/bin/env python3
"""Validate the public Italian tutor template without changing it."""

from __future__ import annotations

import argparse
from pathlib import Path


REQUIRED = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "LICENSE",
    "learner-profile.md",
    "config/daily-briefing.md",
    "records/mastery.md",
    "docs/syllabus.md",
    "session-protocol.md",
    "scripts/controller_model.py",
    "scripts/acceptance.py",
)

FORBIDDEN = (
    "/" + "Users/",
    "private-italian-" + "tutor-records",
    "records/" + "archive",
    "voice" + "-web",
    "Azure " + "Speech",
    "Launch" + "Agent",
    "CI" + "LS",
    "2026-" + "12-03",
    "Wembanya" + "ma",
    "Brun" + "son",
    "Jia" + "jun",
)

REQUIRED_PROTOCOL_TERMS = (
    "Adaptive Controller",
    "Two consecutive independent successes",
    "at most two transfer repairs",
    "unannounced E4 retrieval in a later session",
    "one primary uncertainty",
    "may not silently change the learner's long-term goal",
    "write `Setup Status: Completed` last",
    "HARD GATE",
    "the next correct response is capped at E1",
    "future session; undisclosed",
    "enable the daily briefing by default",
    "never infer the learner's name",
    "moves the point down exactly one level",
    "An announced focus counts as a prompt for sealing",
    "One item credits one point",
    "Independent fully correct: x/y",
    "Stale `Learning` points",
    "never as a separate list",
    "Keep only the most recent 7 log lines",
)


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED:
        if not (root / relative).is_file():
            errors.append(f"Missing required file: {relative}")

    if errors:
        return errors

    text_suffixes = {"", ".md", ".py", ".txt", ".json", ".toml", ".yaml", ".yml"}
    files = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
        and "artifacts" not in path.parts
        and path.suffix in text_suffixes
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)

    for term in FORBIDDEN:
        if term in combined:
            errors.append(f"Forbidden private or retired term found: {term}")

    if "{" + "{" in combined or "}" + "}" in combined:
        errors.append("Unresolved template placeholder found")

    profile = (root / "learner-profile.md").read_text(encoding="utf-8")
    for label in ("Setup Status: Not completed", "Placement Status:", "Working Level:"):
        if label not in profile:
            errors.append(f"Learner profile missing initial field: {label}")

    protocol = (root / "session-protocol.md").read_text(encoding="utf-8")
    for term in REQUIRED_PROTOCOL_TERMS:
        if term not in protocol:
            errors.append(f"Protocol invariant missing: {term}")

    mastery = (root / "records/mastery.md").read_text(encoding="utf-8")
    for section in ("## Route", "## Current queue", "## Mastery ledger", "## Controller state"):
        if section not in mastery:
            errors.append(f"Mastery state missing section: {section}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors = validate(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Template is valid: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
