"""
backend/scripts/push_v2_flip.py
Branch: v5-whatsapp

OBSOLETE as of v6.3.19.1 — the cutover release removed the
PUSH_V2_ENABLED flag entirely and made the new push system the sole
code path. This CLI has no operational effect on a v6.3.19.1+ build:
writing PUSH_V2_ENABLED=true|false to the .env produces an unused
environment variable. The script is retained for historical
reference (and so v6.3.19-era operator runbooks linking to it don't
404). Delete in a future cleanup release once no surviving runbook
references it.

FILE PURPOSE (historical)
v6.3.19 slice 2D-flip — admin CLI to flip the PUSH_V2_ENABLED gate.
Writes PUSH_V2_ENABLED=true | PUSH_V2_ENABLED=false to backend/.env
(or a path passed via --env-file) and reports current state plus a
24h shadow-log count.

This script does NOT itself flip production. It is invoked manually
by ops AFTER the shadow-log verification gate criteria in
docs/v6_3_19_smoke_tests.md are all green. v6.3.19 ships with the
script and the flag default False; v6.3.19.1 is the release where ops
runs `--enable` after verification.

USAGE
    python scripts/push_v2_flip.py --enable
    python scripts/push_v2_flip.py --disable
    python scripts/push_v2_flip.py --status
    python scripts/push_v2_flip.py --enable --env-file path/to/.env

WHO CALLS THIS FILE
- ops, manually, when flipping the cutover gate.
- tests/integration/test_push_v2_flip.py — integration test for the
  script's mechanics.

WHAT THIS FILE CALLS
- argparse for the CLI parsing.
- pathlib.Path for atomic write via tempfile + replace.
- app.database.SessionLocal + app.models.event.Event for the
  shadow-log count in --status.

CONCURRENT-RUN SAFETY
The atomic write (write to a sibling temp file, then os.replace) is
crash-consistent on POSIX and Windows — a partial write cannot leave
a half-written .env. Two simultaneous --enable / --disable runs WILL
race; the last writer wins. Do NOT run two flips concurrently against
the same .env file. Single-operator workflow only.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make the backend root importable when this script is invoked directly
# as `python scripts/push_v2_flip.py` (no -m). Existing diagnostic
# scripts use `python -m scripts.X` which adds cwd to sys.path
# automatically; the path injection here lets ops use either form.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# Default location for backend's .env, relative to this script's parent
# (backend/). Override via --env-file.
_DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

_FLAG_NAME = "PUSH_V2_ENABLED"
_TRUE_LITERAL = "true"
_FALSE_LITERAL = "false"


def _read_env_lines(path: Path) -> list[str]:
    """Read .env lines preserving order; return [] when the file is missing.

    Called by:    set_flag, read_flag.
    Calls into:   pathlib.Path.read_text.
    Side effects: read-only.
    """
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines(keepends=False)


def _atomic_write(path: Path, lines: list[str]) -> None:
    """Write `lines` to `path` via a sibling temp file + os.replace.

    Called by:    set_flag.
    Calls into:   tempfile.NamedTemporaryFile, os.replace.
    Side effects: replaces `path` atomically. The temp file lives in
                  the same directory so os.replace can do a same-filesystem
                  rename.
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=".env.flip.", dir=parent, text=True,
    )
    tmp_path = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
            if lines and not lines[-1].endswith("\n"):
                fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        # Best-effort cleanup on failure; never leave a stray temp.
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def set_flag(value: bool, env_path: Path = _DEFAULT_ENV_PATH) -> str:
    """Write PUSH_V2_ENABLED=<value> to env_path, replacing or appending.

    Called by:    main_cli for --enable / --disable.
    Calls into:   _read_env_lines, _atomic_write.
    Side effects: rewrites env_path (atomic).

    Returns the literal value written ("true" or "false") so the caller
    can echo it.
    """
    literal = _TRUE_LITERAL if value else _FALSE_LITERAL
    new_line = f"{_FLAG_NAME}={literal}"

    lines = _read_env_lines(env_path)
    replaced = False
    for i, line in enumerate(lines):
        # Match the assignment line; tolerate leading whitespace and
        # extra spacing around `=`.
        stripped = line.lstrip()
        if stripped.startswith(f"{_FLAG_NAME}=") or stripped.startswith(
            f"{_FLAG_NAME} ="
        ):
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        lines.append(new_line)

    _atomic_write(env_path, lines)
    return literal


def read_flag(env_path: Path = _DEFAULT_ENV_PATH) -> str | None:
    """Return the literal value of PUSH_V2_ENABLED in env_path, or None
    when the line is missing entirely.

    Called by:    main_cli for --status.
    Calls into:   _read_env_lines.
    Side effects: read-only.
    """
    for line in _read_env_lines(env_path):
        stripped = line.lstrip()
        if stripped.startswith(f"{_FLAG_NAME}="):
            return stripped.split("=", 1)[1].strip()
        if stripped.startswith(f"{_FLAG_NAME} ="):
            return stripped.split("=", 1)[1].strip()
    return None


def count_shadow_logs_last_24h() -> int:
    """Count `push.shadow_log` events written in the last 24 hours.

    Called by:    main_cli for --status.
    Calls into:   app.database.SessionLocal, app.models.event.Event.
    Side effects: opens and closes one DB session.

    Returns 0 when the events table is empty or no rows match.
    Raises ImportError when invoked outside the backend's runtime
    environment (the importable `app` package is required).
    """
    from app.database import SessionLocal
    from app.models.event import Event

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    db = SessionLocal()
    try:
        return (
            db.query(Event)
            .filter(
                Event.event_type == "push.shadow_log",
                Event.created_at >= cutoff,
            )
            .count()
        )
    finally:
        db.close()


def main_cli(argv: list[str] | None = None) -> int:
    """Argparse-driven entry point.

    Called by:    `python scripts/push_v2_flip.py ...` and the
                  integration test.
    Calls into:   set_flag, read_flag, count_shadow_logs_last_24h.
    Side effects: writes to env_path on --enable / --disable; prints
                  to stdout. Does NOT touch the running backend (a
                  restart is required for the new value to take effect).

    Returns the process exit code (0 on success, 1 on misuse).
    """
    parser = argparse.ArgumentParser(
        description="Flip the v6.3.19 PUSH_V2_ENABLED cutover gate.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--enable", action="store_true",
        help="Set PUSH_V2_ENABLED=true in the .env. Backend restart required.",
    )
    group.add_argument(
        "--disable", action="store_true",
        help="Set PUSH_V2_ENABLED=false in the .env. Backend restart required.",
    )
    group.add_argument(
        "--status", action="store_true",
        help=(
            "Print the current PUSH_V2_ENABLED value and the 24h "
            "push.shadow_log event count. Read-only."
        ),
    )
    parser.add_argument(
        "--env-file", type=Path, default=_DEFAULT_ENV_PATH,
        help="Path to the .env file (default: backend/.env).",
    )
    args = parser.parse_args(argv)

    if args.enable:
        literal = set_flag(True, args.env_file)
        print(f"{_FLAG_NAME}={literal} written to {args.env_file}.")
        print("Flag enabled. Restart backend to apply.")
        return 0

    if args.disable:
        literal = set_flag(False, args.env_file)
        print(f"{_FLAG_NAME}={literal} written to {args.env_file}.")
        print("Flag disabled. Restart backend to apply.")
        return 0

    # --status (read-only).
    current = read_flag(args.env_file)
    if current is None:
        print(
            f"{_FLAG_NAME} not present in {args.env_file} "
            f"(implicit default: false)."
        )
    else:
        print(f"{_FLAG_NAME}={current} (in {args.env_file}).")

    try:
        count = count_shadow_logs_last_24h()
    except Exception as exc:  # noqa: BLE001 — diagnostic path
        print(
            f"Could not count push.shadow_log events: {exc.__class__.__name__}: {exc}",
            file=sys.stderr,
        )
        return 0
    print(f"push.shadow_log events in the last 24h: {count}")
    if count == 0 and (current == _TRUE_LITERAL):
        print(
            "WARNING: PUSH_V2_ENABLED=true but zero shadow_log rows in 24h. "
            "Either the new tick is not firing, or the flag was just flipped. "
            "Verify before relying on shadow-log verification.",
            file=sys.stderr,
        )
    elif count == 0:
        print(
            "Note: zero shadow_log rows in 24h. The new tick may not be "
            "firing in this environment, or no tenants are configured for "
            "morning/evening pushes.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
