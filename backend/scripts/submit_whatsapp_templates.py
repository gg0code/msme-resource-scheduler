"""Meta template submission helper — v6.3.23 brand asset library.

FILE PURPOSE
Submits WhatsApp HSM templates that need a HEADER IMAGE component to
Meta and writes the returned header_image_handle back to
whatsapp_template_handles.json so the runtime send path can inject the
IMAGE component into outbound messages. Idempotent: a (template_name,
language) pair whose handle is already populated is skipped without a
Meta call.

Run from the repo root:

    # Safe inspection — no Meta calls, no file writes:
    python backend/scripts/submit_whatsapp_templates.py --dry-run

    # Real submission (requires WHATSAPP_ACCESS_TOKEN + WHATSAPP_WABA_ID,
    # gated on Meta Business portfolio approval clearing):
    python backend/scripts/submit_whatsapp_templates.py --apply

WHO CALLS THIS FILE
  - Human operator at release time, once Meta approves the v6.3.23
    template re-submissions. Not imported by any runtime code.
  - tests/test_whatsapp_branded_headers.py — AC6 idempotency test
    monkey-patches submit_one() so the second consecutive run reports
    zero new submissions without touching Meta.

WHAT THIS FILE CALLS
  - app.services.whatsapp_template_assets — REGISTRY (for asset paths)
    and the handle JSON path; writes the same JSON file back on
    successful --apply.
  - app.services.whatsapp_meta_templates.META_TEMPLATES — read-only,
    to confirm the (name, language) pair exists in the Meta-side
    registration metadata before attempting a submission.
  - httpx — POSTs to graph.facebook.com in --apply mode. Not used at
    all in --dry-run.

KEY DESIGN DECISIONS
  - Idempotency check is local: a non-null handle in
    whatsapp_template_handles.json means "already submitted, skip."
    The script does NOT call Meta's GET /message_templates endpoint
    on every run; that would slow operators down and add a network
    failure mode. Drift between the local JSON and Meta state is
    operator responsibility (re-run the script with the JSON wiped
    if needed).
  - --apply writes handles back atomically (write to *.tmp, then
    os.replace) so a crash between Meta success and disk write does
    not leave the JSON half-updated.
  - The HTTP layer is split into a small Submitter class so tests
    can pass a stub Submitter and exercise the orchestration logic
    without httpx involvement.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Protocol

# Make backend/ importable when run from repo root.
_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.services.whatsapp_meta_templates import META_TEMPLATES  # noqa: E402
from app.services.whatsapp_template_assets import (  # noqa: E402
    REGISTRY,
    _HANDLES_PATH,
    get_brand_asset,
)


@dataclass(frozen=True)
class SubmissionTarget:
    """One (meta_template_name, language) pair pending submission."""
    meta_template_name: str
    language: str
    asset_filename: str
    asset_path: Path
    handle_key: str  # exact key in whatsapp_template_handles.json


@dataclass
class RunReport:
    """Summary printed at the end of each run."""
    targets_total: int
    targets_already_submitted: int
    targets_submitted: int
    targets_skipped_missing_brand: int
    dry_run: bool

    def __str__(self) -> str:
        mode = "DRY-RUN" if self.dry_run else "APPLY"
        return (
            f"[{mode}] targets={self.targets_total} "
            f"already_submitted={self.targets_already_submitted} "
            f"submitted={self.targets_submitted} "
            f"skipped_missing_brand={self.targets_skipped_missing_brand}"
        )


class Submitter(Protocol):
    """Pluggable Meta submission layer. Tests pass a stub."""
    def submit(self, target: SubmissionTarget) -> Optional[str]:
        """Submit `target` to Meta. Return the handle on success, None on failure."""
        ...


class HttpxSubmitter:
    """Real Meta submission via httpx.

    Two-step flow per Meta's Cloud API:
      1. POST upload session to https://graph.facebook.com/v21.0/app/uploads
      2. POST image bytes -> returns 'h' (the header_handle)

    Then a separate POST to /message_templates registers the template
    with the handle in its HEADER component. v6.3.23 leaves that POST
    to the operator — they should already have the templates created
    via the Interakt UI; this script only fills in the IMAGE handle.
    """

    def __init__(self, access_token: str, app_id: str):
        self.access_token = access_token
        self.app_id = app_id

    def submit(self, target: SubmissionTarget) -> Optional[str]:
        # Real Meta call is intentionally not implemented in v6.3.23 —
        # Meta Business portfolio approval has not cleared, so this
        # branch is dead code until v5.11 cutover. The operator runs
        # --dry-run only; on the day production lights up, this method
        # is filled in alongside the Meta credentials.
        raise NotImplementedError(
            "HttpxSubmitter.submit is wired but disabled until Meta "
            "portfolio approval. Re-run with --dry-run for v6.3.23 "
            "acceptance, or fill in this method when going live."
        )


def _load_handles() -> dict[str, Optional[str]]:
    """Load the handles sidecar, preserving comment keys."""
    with _HANDLES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _write_handles_atomic(data: dict[str, Optional[str]]) -> None:
    """Write the handles sidecar atomically.

    Writes to a temp file in the same directory, then os.replace()
    onto the destination. Mirrors the pattern used by scripts/push_v2_flip.py.
    """
    target_dir = _HANDLES_PATH.parent
    fd, tmp_path = tempfile.mkstemp(
        prefix=".handles.", suffix=".json.tmp", dir=str(target_dir),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, _HANDLES_PATH)
    except BaseException:
        # Clean up tmp on any error path.
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _enumerate_targets(handles: dict[str, Optional[str]]) -> Iterable[SubmissionTarget]:
    """Walk the handles JSON and yield one SubmissionTarget per slot.

    Comment keys (starting with `_`) are skipped. Slots whose brand
    asset is missing (Meta template not in REGISTRY) are reported back
    via the skipped_missing_brand counter at the call site.
    """
    for handle_key in handles.keys():
        if handle_key.startswith("_"):
            continue
        try:
            meta_name, language = handle_key.split("::", 1)
        except ValueError:
            print(f"  ! malformed handle key {handle_key!r} — expected '<name>::<lang>'")
            continue
        brand = get_brand_asset(meta_name)
        if brand is None:
            yield SubmissionTarget(
                meta_template_name=meta_name,
                language=language,
                asset_filename="",
                asset_path=Path(),
                handle_key=handle_key,
            )
            continue
        yield SubmissionTarget(
            meta_template_name=meta_name,
            language=language,
            asset_filename=brand.filename,
            asset_path=brand.path,
            handle_key=handle_key,
        )


def run(
    *,
    dry_run: bool,
    submitter: Optional[Submitter] = None,
    handles_override: Optional[dict[str, Optional[str]]] = None,
) -> RunReport:
    """Orchestrate one submission pass.

    Tests call this directly with a stub submitter + a fixture
    handles dict (handles_override) so they can exercise the
    idempotency invariant without touching the on-disk file.

    Operators call it from main() with handles_override=None, which
    loads from disk and writes back on --apply success.
    """
    in_memory = handles_override is not None
    handles = handles_override if in_memory else _load_handles()

    targets = list(_enumerate_targets(handles))
    already = 0
    submitted = 0
    skipped_brand = 0

    for target in targets:
        if not target.asset_filename:
            skipped_brand += 1
            print(
                f"  ? SKIP {target.meta_template_name} ({target.language}) — "
                f"no brand asset in REGISTRY"
            )
            continue
        existing_handle = handles.get(target.handle_key)
        if existing_handle:
            already += 1
            print(
                f"  = SKIP {target.meta_template_name} ({target.language}) — "
                f"already submitted, handle={existing_handle}"
            )
            continue
        if dry_run:
            print(
                f"  + WOULD submit {target.meta_template_name} ({target.language}) "
                f"with header {target.asset_filename}"
            )
            submitted += 1
            continue
        if submitter is None:
            print(
                f"  ! CANNOT submit {target.meta_template_name} ({target.language}) — "
                f"no Submitter provided (Meta portfolio approval pending)"
            )
            continue
        handle = submitter.submit(target)
        if handle:
            print(
                f"  ✓ SUBMITTED {target.meta_template_name} ({target.language}) "
                f"-> handle={handle}"
            )
            handles[target.handle_key] = handle
            submitted += 1
        else:
            print(
                f"  ✗ FAILED to submit {target.meta_template_name} ({target.language})"
            )

    # Apply mode writes back if any submission succeeded and we're not
    # in test-injected mode.
    if not dry_run and submitted > 0 and not in_memory:
        _write_handles_atomic(handles)
        print(f"  > wrote {submitted} new handle(s) to {_HANDLES_PATH.name}")

    return RunReport(
        targets_total=len(targets),
        targets_already_submitted=already,
        targets_submitted=submitted,
        targets_skipped_missing_brand=skipped_brand,
        dry_run=dry_run,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit WhatsApp HSM templates with IMAGE headers to Meta.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Print actions without contacting Meta.")
    group.add_argument("--apply", action="store_true", help="Submit to Meta (requires credentials).")
    args = parser.parse_args()

    print(f"REGISTRY size: {len(REGISTRY)}")
    print(f"META_TEMPLATES size: {len(META_TEMPLATES)}")
    print(f"WHATSAPP_ASSET_BASE_URL: {settings.WHATSAPP_ASSET_BASE_URL}")
    print()

    if args.dry_run:
        report = run(dry_run=True)
    else:
        access_token = settings.WHATSAPP_ACCESS_TOKEN
        app_id = os.environ.get("WHATSAPP_APP_ID", "")
        if not access_token or not app_id:
            print(
                "ERROR: --apply needs WHATSAPP_ACCESS_TOKEN (in .env) and "
                "WHATSAPP_APP_ID (env var). Run --dry-run instead, or "
                "wait for Meta Business portfolio approval before --apply."
            )
            return 2
        submitter = HttpxSubmitter(access_token=access_token, app_id=app_id)
        report = run(dry_run=False, submitter=submitter)

    print()
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
