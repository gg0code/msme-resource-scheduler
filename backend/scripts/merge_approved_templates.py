# scripts/merge_approved_templates.py
# Branch: v5-whatsapp
# Iteration: v6.3.21 follow-up
#
# FILE PURPOSE
# One-shot reconciliation script that clears in-flight status flags
# from app/services/whatsapp_meta_templates.json after Meta approves
# the pending templates upstream. Idempotent — a second run finds
# zero flagged entries and reports `cleared 0`.
#
# WHO CALLS THIS FILE
# - Operator / release engineering, manually, post Meta approval.
#   Never imported, never run from production code paths.
#
# WHAT THIS FILE CLEARS
# Any registry entry whose top-level `status` field equals one of:
#   - "draft_pending_meta_submission"  (v6.3.21 wiring era; pre-submission)
#   - "pending_meta_approval"          (Day-7 + give-up-nudge wiring;
#                                       post-submission, pre-approval)
# A live (Meta-approved) entry has no `status` field; an in-flight
# entry carries one of the strings above. The script walks the registry,
# pops the field where present, and writes the file back.
#
# USAGE
#   python3 scripts/merge_approved_templates.py app/services/whatsapp_meta_templates.json
#
# The second-argument batch-file slot from earlier drafts is intentionally
# absent: the script does NOT append new entries any more — appending is
# now a manual editor task, since the body text + example block needs
# human review before commit. The script is purely a status-flag cleanup
# step.

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CLEARED_FLAGS: frozenset[str] = frozenset({
    "draft_pending_meta_submission",
    "pending_meta_approval",
})


def main(argv: list[str]) -> int:
    """Clear in-flight status flags from the registry JSON.

    Called by:    operator CLI invocation only.
    Calls into:   json (stdlib), pathlib (stdlib).
    Side effects: rewrites the registry JSON file in place.
                  Prints one-line summaries to stdout.

    Exit codes:
        0  Success (zero or more flags cleared; either is normal).
        1  Registry file missing or unreadable.
        2  Registry JSON malformed.
    """
    parser = argparse.ArgumentParser(
        description="Clear in-flight Meta-template status flags after approval.",
    )
    parser.add_argument(
        "registry_path",
        type=Path,
        help="Path to whatsapp_meta_templates.json",
    )
    args = parser.parse_args(argv)

    registry_path: Path = args.registry_path

    if not registry_path.exists():
        print(f"ERROR: registry file not found: {registry_path}", file=sys.stderr)
        return 1

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: {registry_path} is not valid JSON: {exc}", file=sys.stderr)
        return 2

    cleared = 0
    for entry in registry:
        if entry.get("status") in CLEARED_FLAGS:
            del entry["status"]
            cleared += 1
    print(f"Step 1: cleared {cleared} pending status flag(s) on existing entries.")

    print("Step 2: appended 0 new entries.")

    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    print(f"Registry updated: {registry_path} (now {len(registry)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
