"""
```python
"""
ZetaOps Copilot Documentation Generator
=======================================

FILE PURPOSE
This is an automated documentation generator script that systematically walks through 
the entire ZetaOps Copilot codebase, sends each source file to Claude AI API for 
analysis, and injects comprehensive header comments back into the files. This utility 
was introduced to maintain consistent, detailed documentation for new developers 
joining the project. It exists at the repository root level and operates as a 
standalone development tool, separate from the main application architecture.

WHAT THIS FILE DOES — step by step
1. Parses command-line arguments to determine which files/folders to process
2. Loads ANTHROPIC_API_KEY from backend/.env file or environment variables
3. Recursively discovers all Python/TypeScript/JavaScript files in the codebase
4. Filters out irrelevant files (node_modules, __pycache__, empty __init__.py, etc.)
5. For each source file, constructs a detailed prompt containing project context
6. Sends the file content and context to Claude AI via Anthropic API
7. Receives back a comprehensive header comment tailored for new interns
8. Injects the generated comment at the top of the original file
9. Implements rate limiting and retry logic to respect API quotas
10. Generates README.txt files for each processed directory
11. Provides dry-run mode for preview without making actual changes

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : load_api_key
Type         : function
Purpose      : Securely loads the Anthropic API key from backend/.env file with fallback to system environment variables. Validates the key format and provides helpful error messages if missing.
Parameters   : None
Returns      : str - the validated ANTHROPIC_API_KEY starting with 'sk-ant-'
Calls        : dotenv_values() from python-dotenv, os.environ.get()
DB/API       : No database calls, reads local .env file
Side effects : Exits the program with sys.exit(1) if API key is not found or invalid

Name         : should_skip_file
Type         : function
Purpose      : Determines whether a specific file should be excluded from documentation based on filename patterns, file type, and content analysis. Prevents processing of configuration files and empty Python packages.
Parameters   : path (Path) - pathlib.Path object representing the file to check
Returns      : bool - True if file should be skipped, False if it should be documented
Calls        : Path.read_text() for content inspection
DB/API       : No external calls, only local file system reads
Side effects : May read file content to check if __init__.py files are empty

Name         : should_skip_dir
Type         : function
Purpose      : Identifies directories that should be completely excluded from the documentation process, such as dependency folders, build artifacts, and version control directories.
Parameters   : dir_path (Path) - pathlib.Path object representing the directory to check
Returns      : bool - True if entire directory should be skipped, False otherwise
Calls        : None, only checks directory name against SKIP_DIRS set
DB/API       : No external calls
Side effects : None, pure function

WHO CALLS THIS FILE
This is a standalone script executed directly from the command line. It is not imported 
by any other files in the codebase. Developers and CI/CD pipelines may invoke it using:
- python generate_docs.py (from repository root)
- Called manually during development to refresh documentation
- Potentially integrated into pre-commit hooks or CI workflows

IMPORTS EXPLAINED
- os: Operating system interface for environment variable access and file system operations
- sys: System-specific parameters, used for sys.exit() on error conditions
- re: Regular expression operations (imported but may be used for text processing)
- time: Time-related functions for implementing rate limiting between API calls
- argparse: Command-line argument parsing to handle --branch, --path, --dry-run flags
- asyncio: Asynchronous I/O support (imported but current implementation appears synchronous)
- textwrap: Text wrapping utilities for formatting generated documentation
- pathlib.Path: Modern path handling for cross-platform file system operations
- datetime: Date and time handling for timestamps in generated documentation
- concurrent.futures: ThreadPoolExecutor for potential parallel processing of files
- typing.Optional: Type hints for better code maintainability
- anthropic: Official Anthropic API client for Claude AI integration
- dotenv.dotenv_values: Secure loading of environment variables from .env files

INTERN NOTES
- Easiest thing to break without realising: Modifying RATE_LIMIT_SLEEP or PARALLEL_WORKERS without understanding API quotas - Claude has strict rate limits and increasing parallelism or reducing delays can cause 429 errors and failed documentation runs
- Non-obvious design decision and why: The script uses a single worker (PARALLEL_WORKERS = 1) and 20-second delays between files to stay well under Claude's 4k tokens/minute rate limit, prioritizing reliability over speed since documentation generation is not time-critical
- Most common mistake when editing: Changing the PROJECT_CONTEXT string without testing - this context is injected into every AI prompt and even small changes can dramatically affect the quality and consistency of generated documentation across all files
- Which design principle (by number) this file implements: Principle #3 (No .env in git. All secrets from settings.*) - the script securely loads API keys from backend/.env and provides clear error messages when credentials are missing
- What to check if this file behaves unexpectedly: First verify ANTHROPIC_API_KEY is valid in backend/.env, then check if you're hitting rate limits (429 errors), and ensure the target files have proper encoding and aren't corrupted
- If v5-whatsapp only: This is a development tool that works across all branches - when documenting v5-whatsapp specific files, ensure the generated comments clearly indicate WhatsApp-only features and potential merge conflicts with v4-dev
"""
```
"""

import os
import sys
import re
import time
import argparse
import asyncio
import textwrap
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic python-dotenv")
    sys.exit(1)

try:
    from dotenv import dotenv_values
except ImportError:
    print("ERROR: python-dotenv not installed. Run: pip install anthropic python-dotenv")
    sys.exit(1)


# ─── Configuration ────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.resolve()
ENV_FILE  = REPO_ROOT / "backend" / ".env"

# Files to process by extension
SUPPORTED_EXTENSIONS = {
    ".py":  "python",
    ".ts":  "typescript",
    ".tsx": "typescript",
    ".js":  "javascript",
    ".jsx": "javascript",
}

# Folders to skip entirely
SKIP_DIRS = {
    "node_modules", "venv", ".venv", "__pycache__", ".git",
    "dist", "build", ".next", "coverage", ".pytest_cache",
    "migrations",  # skip raw alembic env files
}

# Individual filenames to skip
SKIP_FILES = {
    "vite.config.ts", "tailwind.config.ts", "postcss.config.js",
    "eslint.config.js", ".eslintrc.js", "jest.config.ts",
    "setupTests.ts", "react-app-env.d.ts",
}

# Folders within alembic to skip (keep versions for docs if desired)
SKIP_ALEMBIC_ENV = {"alembic/env.py"}

PARALLEL_WORKERS = 1        # 1 = safe for 4k output tokens/min limit
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 1800           # well under 4k/min limit, still enough for good docs
RATE_LIMIT_SLEEP = 20       # seconds between files — gives token bucket time to refill
RETRY_ATTEMPTS = 4          # retry on 429 before giving up
RETRY_BASE_DELAY = 60       # seconds to wait on first 429 (doubles each retry)

# ─── Project context (injected into every prompt) ─────────────────────────────

PROJECT_CONTEXT = """
PROJECT CONTEXT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Project   : ZetaOps Copilot (formerly MSME Resource Scheduler)
Purpose   : AI-powered workforce and job scheduling web app for small/medium
            manufacturing businesses. Supports printing, corrugated box
            manufacturing, fabrication, chemical processing, and field service.
Version   : v4.0.9 (production) / v5.x (WhatsApp Copilot)
Repo      : https://github.com/gg0code/msme-resource-scheduler
Branches  :
  v4-dev       — production-stable. All bug fixes land here first.
  v5-whatsapp  — WhatsApp Copilot feature branch. Built on top of v4-dev.
  master       — release branch.

Tech Stack:
  Backend  — Python 3.14, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL
             Groq LLaMA 3.3-70b for AI Copilot
             Groq Whisper large-v3 for WhatsApp voice transcription (v5)
             Interakt for WhatsApp delivery (v5)
  Frontend — React 18, TypeScript strict mode, Vite, TailwindCSS,
             TanStack Query, Axios
  Auth     — JWT access token in memory (tokenStore), refresh in httpOnly cookie

Folder roles:
  backend/app/routers/        FastAPI route handlers, all /api/ prefix
  backend/app/models/         SQLAlchemy ORM models, all have tenant_id
  backend/app/schemas/        Pydantic v2 request/response shapes
  backend/app/services/       Business logic and WhatsApp services
  backend/app/scheduler/      Core scheduling engine, pure Python, zero DB calls
  backend/app/core/           security.py, plan_limits.py, dependencies.py
  backend/app/crud/           DB query functions, always filter by tenant_id
  backend/app/utils/          feature_guard, csv_import, date_utils
  backend/app/tasks/          auto_advance.py background loop
  backend/alembic/versions/   18 migrations, single chain, head=018
  frontend/src/pages/         One component per screen
  frontend/src/components/    Reusable UI components
  frontend/src/api/           Axios API functions (named api_*.ts)
  frontend/src/types/         types_index.ts — all shared TypeScript types
  frontend/src/auth/          Auth context and Axios client
  frontend/src/context/       FeatureFlags.tsx, IndustryContext.tsx

Key files:
  backend/app/main.py                      — entry point, all routers registered
  backend/app/scheduler/engine.py          — greedy priority scheduler, pure Python
  backend/app/services/availability_engine.py — tenant-scoped availability checks
  backend/app/services/ai_service.py       — Groq/LLaMA, AI narrates only
  backend/app/routers/scheduler_router.py  — loads from DB, calls engine, persists
  backend/app/core/dependencies.py         — get_current_user, require_role, get_db
  backend/app/utils/feature_guard.py       — require_feature() gating
  backend/app/features_config.py           — FEATURE_FLAGS dict
  frontend/src/types/types_index.ts        — ALL shared TypeScript types
  frontend/src/api/client.ts               — Axios instance, tokenStore, refresh

Data models (key fields):
  Tenant   — id, slug, plan, industry_type, ai_queries_today
  User     — id, tenant_id, email, hashed_password, role
  Job      — id, tenant_id, name, priority, status, start_date, end_date,
             raw_materials (JSON), timer_status, is_locked, job_type, quantity
  JobStep  — id, job_id, tenant_id, sequence_no, name, step_type,
             duration_minutes, status, started_at
  JobAssignment — id, job_id, employee_id, machine_id, tenant_id, allocation_pct
  Employee — id, tenant_id, full_name, base_availability_pct, hourly_rate
  Machine  — id, tenant_id, name, machine_type, status, hourly_rate
  PhoneTenantMap        — phone_number → tenant mapping (v5 only)
  WhatsAppConversation  — message log for Factory GPT training (v5 only)

Design principles:
  1. Engine computes, AI only narrates. LLM never re-computes logic.
  2. Tenant scoping on ALL DB queries. Missing filter = security bug.
  3. No .env in git. All secrets from settings.*.
  4. /api/ prefix on all backend routes.
  5. Skill gaps (amber) != Scheduling conflicts (red).
  6. Scheduler reads Job/JobStep/Machine/Employee, NOT legacy SchedJob tables.
  7. Steps fall back to job-level resources if no step resources set.
  8. Feature flags gate all optional features via FEATURE_FLAGS.
  9. WhatsApp services use sync Session. Bridge uses run_in_executor().
 10. QR scan verify/execute never feature-flagged. Only generation is gated.
 11. TypeScript strict mode enforced. tsc --noEmit zero errors required.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ─── Prompt templates ─────────────────────────────────────────────────────────

HEADER_PROMPT = """You are documenting a codebase for a NEW INTERN who has never seen this project.
Be explicit. Assume nothing is obvious. Be verbose.

{project_context}

FILE TO DOCUMENT:
  Path   : {file_path}
  Branch : {branch}
  Language: {language}

SOURCE CODE:
{source_code}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Write a header comment to go at the TOP of this file.
Use the correct comment style:
  Python           →  triple-quoted string: \"\"\" ... \"\"\"
  TypeScript / TSX →  /** ... */

Include these sections:

FILE PURPOSE
  One paragraph. What this file does, why it exists, which version/branch
  introduced it, and where it sits in the architecture.

WHAT THIS FILE DOES — step by step
  Numbered list walking through the file top to bottom.

KEY FUNCTIONS / CLASSES / COMPONENTS
  For EVERY exported function, class, endpoint, React component, or hook:
    Name         : exact name
    Type         : function / class / FastAPI endpoint / React component / hook
    Purpose      : 2-4 sentences
    Parameters   : each param with type and meaning
    Returns      : what it returns and what that means to the caller
    Calls        : which other files/functions it calls
    DB/API       : any DB queries or external API calls
    Side effects : anything it writes, emits, or modifies

WHO CALLS THIS FILE
  Specific files by relative path that import or call this file.

IMPORTS EXPLAINED
  Every import with one sentence: what it is and why this file needs it.

INTERN NOTES
  6 bullet points:
  - Easiest thing to break without realising
  - Non-obvious design decision and why
  - Most common mistake when editing
  - Which design principle (by number) this file implements
  - What to check if this file behaves unexpectedly
  - If v5-whatsapp only: what to know when merging into v4-dev

OUTPUT RULES:
- Output ONLY the comment block. No explanation before or after it.
- Do not include the source code in your output.
- Be verbose. An intern must fully understand this file from the comment alone.
- Reference design principles by number.
"""

README_PROMPT = """You are documenting a codebase folder for a NEW INTERN.

{project_context}

FOLDER: {folder_path}
BRANCH: {branch}

FILES IN THIS FOLDER:
{file_summaries}

Write a README.txt for this folder. Plain text only, no markdown.

Include:
  FOLDER: {folder_path}
  BRANCH: v4-dev | v5-whatsapp | both
  PURPOSE: one sentence describing what this folder contains
  
  FILES:
    For each file — filename, one-line purpose, branch it belongs to
  
  ARCHITECTURE NOTES:
    3-5 sentences on how the files in this folder relate to each other
    and how this folder fits into the overall system.
  
  DESIGN PRINCIPLES:
    Which numbered principles apply to this folder and how.
  
  GOTCHAS:
    3 things an intern must know before editing any file in this folder.
  
  DEPENDENCIES:
    What this folder depends on (other folders/files it imports from).
    What depends on this folder (other folders/files that import from it).

OUTPUT: plain text only. No markdown. No asterisks. No hashes.
"""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_api_key() -> str:
    """Load ANTHROPIC_API_KEY from backend/.env"""
    if not ENV_FILE.exists():
        print(f"ERROR: {ENV_FILE} not found.")
        print("Make sure backend/.env exists and contains ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    env = dotenv_values(ENV_FILE)
    key = env.get("ANTHROPIC_API_KEY", "").strip()

    if not key or not key.startswith("sk-ant-"):
        # Also check system environment as fallback
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    if not key:
        print("ERROR: ANTHROPIC_API_KEY not found in backend/.env")
        print("Add this line to backend/.env:  ANTHROPIC_API_KEY=sk-ant-your-key-here")
        sys.exit(1)

    return key


def should_skip_file(path: Path) -> bool:
    """Return True if this file should not be documented."""
    # Skip by filename
    if path.name in SKIP_FILES:
        return True
    # Skip __init__.py if empty
    if path.name == "__init__.py":
        content = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not content:
            return True
    # Skip alembic env.py
    for skip in SKIP_ALEMBIC_ENV:
        if str(path).replace("\\", "/").endswith(skip):
            return True
    return False


def should_skip_dir(dir_path: Path) -> bool:
    """Return True if this directory should be skipped entirely."""
    return dir_path.name in SKIP_DIRS


def detect_branch(repo_root: Path) -> str:
    """Try to detect current git branch, default to v4-dev."""
    try:
        head = (repo_root / ".git" / "HEAD").read_text().strip()
        if "v5-whatsapp" in head:
            return "v5-whatsapp"
        if "v4-dev" in head:
            return "v4-dev"
        if "master" in head:
            return "master"
    except Exception:
        pass
    return "v4-dev"


def get_comment_markers(language: str) -> tuple[str, str, str]:
    """Return (open_marker, close_marker, line_prefix) for the language."""
    if language == "python":
        return ('"""', '"""', "")
    else:  # typescript, javascript
        return ("/**", " */", " * ")


def strip_existing_header(content: str, language: str) -> str:
    """Remove the existing header comment from file content."""
    content = content.lstrip()

    if language == "python":
        # Remove leading triple-quoted docstring
        if content.startswith('"""'):
            end = content.find('"""', 3)
            if end != -1:
                return content[end + 3:].lstrip()
        if content.startswith("'''"):
            end = content.find("'''", 3)
            if end != -1:
                return content[end + 3:].lstrip()

    else:  # typescript/javascript
        # Remove leading /** ... */ block
        if content.startswith("/**"):
            end = content.find("*/")
            if end != -1:
                return content[end + 2:].lstrip()
        # Remove leading // comment block
        lines = content.split("\n")
        i = 0
        while i < len(lines) and lines[i].strip().startswith("//"):
            i += 1
        if i > 0:
            return "\n".join(lines[i:]).lstrip()

    return content


def format_header(raw_comment: str, language: str) -> str:
    """Ensure the comment has correct open/close markers."""
    raw = raw_comment.strip()

    if language == "python":
        if not raw.startswith('"""'):
            raw = '"""\n' + raw
        if not raw.endswith('"""'):
            raw = raw + '\n"""'
        return raw + "\n"
    else:
        if not raw.startswith("/**"):
            raw = "/**\n" + raw
        if not raw.endswith("*/"):
            raw = raw + "\n */"
        return raw + "\n"


def call_claude(client: anthropic.Anthropic, prompt: str) -> str:
    """Call Claude API with exponential backoff retry on 429 rate limit errors."""
    delay = RETRY_BASE_DELAY
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except anthropic.RateLimitError as e:
            if attempt == RETRY_ATTEMPTS:
                raise
            print(f"      [rate limit] 429 — waiting {delay}s then retry {attempt}/{RETRY_ATTEMPTS-1}...")
            time.sleep(delay)
            delay *= 2
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                if attempt == RETRY_ATTEMPTS:
                    raise
                print(f"      [overloaded] 529 — waiting {delay}s then retry {attempt}/{RETRY_ATTEMPTS-1}...")
                time.sleep(delay)
                delay *= 2
            else:
                raise


# ─── Core processors ──────────────────────────────────────────────────────────

def document_file(
    client: anthropic.Anthropic,
    file_path: Path,
    repo_root: Path,
    branch: str,
    dry_run: bool,
    skip_existing: bool,
) -> dict:
    """
    Process a single file:
    1. Read source
    2. Call Claude for header comment
    3. Strip old header, inject new one
    4. Write back to file (unless dry_run)
    Returns a result dict with status and summary.
    """
    rel_path = file_path.relative_to(repo_root)
    ext = file_path.suffix.lower()
    language = SUPPORTED_EXTENSIONS.get(ext, "python")

    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"path": str(rel_path), "status": "error", "reason": f"Read error: {e}"}

    # Skip if already documented and skip_existing is set
    if skip_existing:
        stripped = source.lstrip()
        if language == "python" and stripped.startswith('"""'):
            return {"path": str(rel_path), "status": "skipped", "reason": "already has header"}
        if language in ("typescript", "javascript") and stripped.startswith("/**"):
            return {"path": str(rel_path), "status": "skipped", "reason": "already has header"}

    # Skip very small files (likely empty or just imports)
    if len(source.strip()) < 50:
        return {"path": str(rel_path), "status": "skipped", "reason": "file too small"}

    # Build prompt
    prompt = HEADER_PROMPT.format(
        project_context=PROJECT_CONTEXT,
        file_path=str(rel_path).replace("\\", "/"),
        branch=branch,
        language=language,
        source_code=source[:12000],  # cap at ~12k chars to stay within context
    )

    if dry_run:
        return {"path": str(rel_path), "status": "dry-run", "reason": "would document"}

    # Call Claude
    try:
        raw_comment = call_claude(client, prompt)
    except Exception as e:
        return {"path": str(rel_path), "status": "error", "reason": f"API error: {e}"}

    # Sleep after every successful call to let token bucket refill
    time.sleep(RATE_LIMIT_SLEEP)

    # Format and inject
    header = format_header(raw_comment, language)
    body   = strip_existing_header(source, language)
    new_content = header + "\n" + body

    try:
        file_path.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return {"path": str(rel_path), "status": "error", "reason": f"Write error: {e}"}

    # Extract one-line summary for README (first non-empty line after FILE PURPOSE)
    summary = _extract_summary(raw_comment)
    return {"path": str(rel_path), "status": "ok", "summary": summary}


def _extract_summary(comment: str) -> str:
    """Pull a one-line summary from the generated comment."""
    lines = comment.split("\n")
    capture = False
    for line in lines:
        stripped = line.strip().lstrip("*").strip()
        if "FILE PURPOSE" in stripped.upper():
            capture = True
            continue
        if capture and stripped and not stripped.startswith("WHAT THIS") and not stripped.startswith("KEY "):
            return stripped[:120]
    return "(no summary)"


def document_folder(
    client: anthropic.Anthropic,
    folder: Path,
    file_results: list[dict],
    repo_root: Path,
    branch: str,
    dry_run: bool,
) -> None:
    """Generate and write README.txt for a folder."""
    rel_folder = folder.relative_to(repo_root)

    # Build file summaries from results
    summaries = []
    for r in file_results:
        if r["status"] == "ok":
            fname = Path(r["path"]).name
            summaries.append(f"  {fname}: {r.get('summary', '(see file header)')}")
        elif r["status"] == "skipped":
            fname = Path(r["path"]).name
            summaries.append(f"  {fname}: (skipped — {r.get('reason', '')})")

    if not summaries:
        return

    file_summaries_text = "\n".join(summaries)

    prompt = README_PROMPT.format(
        project_context=PROJECT_CONTEXT,
        folder_path=str(rel_folder).replace("\\", "/"),
        branch=branch,
        file_summaries=file_summaries_text,
    )

    if dry_run:
        print(f"  [dry-run] Would write README.txt → {rel_folder}/")
        return

    try:
        raw = call_claude(client, prompt)
    except Exception as e:
        print(f"  [error] README for {rel_folder}: {e}")
        return

    readme_path = folder / "README.txt"
    header_line = (
        f"AUTO-GENERATED by generate_docs.py on {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"Branch: {branch}\n"
        f"{'─' * 60}\n\n"
    )
    readme_path.write_text(header_line + raw, encoding="utf-8")
    print(f"  [readme] {rel_folder}/README.txt")


# ─── Walker ───────────────────────────────────────────────────────────────────

def collect_files(root: Path) -> dict[Path, list[Path]]:
    """
    Walk root recursively.
    Returns dict: folder → [list of files to document in that folder]
    """
    folder_files: dict[Path, list[Path]] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        dirpath = Path(dirpath)

        # Prune skipped dirs in-place so os.walk doesn't descend into them
        dirnames[:] = [
            d for d in dirnames
            if not should_skip_dir(dirpath / d)
        ]

        files = []
        for fname in filenames:
            fpath = dirpath / fname
            if fpath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if should_skip_file(fpath):
                continue
            files.append(fpath)

        if files:
            folder_files[dirpath] = files

    return folder_files


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ZetaOps Copilot — Documentation Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python generate_docs.py
          python generate_docs.py --branch v5-whatsapp
          python generate_docs.py --path backend/app/routers
          python generate_docs.py --dry-run
          python generate_docs.py --skip-existing
        """)
    )
    parser.add_argument("--branch",        default=None,  help="Branch label (v4-dev or v5-whatsapp). Auto-detected if omitted.")
    parser.add_argument("--path",          default=None,  help="Relative path to a single folder. Defaults to entire repo.")
    parser.add_argument("--dry-run",       action="store_true", help="Preview what would be documented without writing any files.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip files that already have a header comment.")
    args = parser.parse_args()

    print("\n═══════════════════════════════════════════════════")
    print("  ZetaOps Copilot — Documentation Generator")
    print("═══════════════════════════════════════════════════\n")

    # Load API key
    api_key = load_api_key()
    client  = anthropic.Anthropic(api_key=api_key)

    # Detect branch
    branch = args.branch or detect_branch(REPO_ROOT)
    print(f"  Branch  : {branch}")
    print(f"  Dry run : {args.dry_run}")
    print(f"  Workers : {PARALLEL_WORKERS}")

    # Determine root to walk
    walk_root = REPO_ROOT
    if args.path:
        walk_root = REPO_ROOT / args.path
        if not walk_root.exists():
            print(f"ERROR: path not found: {walk_root}")
            sys.exit(1)

    print(f"  Root    : {walk_root.relative_to(REPO_ROOT)}\n")

    # Collect all files grouped by folder
    folder_files = collect_files(walk_root)
    total_files  = sum(len(v) for v in folder_files.values())
    total_folders = len(folder_files)

    print(f"  Found {total_files} files across {total_folders} folders.\n")

    if total_files == 0:
        print("Nothing to document. Exiting.")
        sys.exit(0)

    # Process folder by folder
    grand_total = {"ok": 0, "skipped": 0, "error": 0}
    all_errors  = []

    for folder_idx, (folder, files) in enumerate(sorted(folder_files.items()), 1):
        rel_folder = folder.relative_to(REPO_ROOT)
        print(f"[{folder_idx}/{total_folders}] {rel_folder}/ ({len(files)} files)")

        folder_results = []

        # Process files in parallel batches of PARALLEL_WORKERS
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {
                executor.submit(
                    document_file,
                    client, f, REPO_ROOT, branch, args.dry_run, args.skip_existing
                ): f
                for f in files
            }

            for future in as_completed(futures):
                result = future.result()
                folder_results.append(result)
                status = result["status"]
                fname  = Path(result["path"]).name

                if status == "ok":
                    grand_total["ok"] += 1
                    print(f"    ✓  {fname}")
                elif status == "skipped":
                    grand_total["skipped"] += 1
                    print(f"    –  {fname}  ({result.get('reason', '')})")
                elif status == "dry-run":
                    grand_total["skipped"] += 1
                    print(f"    ~  {fname}  [dry-run]")
                elif status == "error":
                    grand_total["error"] += 1
                    reason = result.get("reason", "unknown error")
                    print(f"    ✗  {fname}  ERROR: {reason}")
                    all_errors.append(f"{result['path']}: {reason}")

        # Write README.txt for this folder (after all files done)
        if not args.dry_run:
            time.sleep(RATE_LIMIT_SLEEP)  # brief pause before README call

        document_folder(client, folder, folder_results, REPO_ROOT, branch, args.dry_run)

        # Pause between folders to respect rate limits
        if folder_idx < total_folders:
            time.sleep(RATE_LIMIT_SLEEP)

        print()

    # Final summary
    print("═══════════════════════════════════════════════════")
    print("  COMPLETE")
    print("═══════════════════════════════════════════════════")
    print(f"  Documented : {grand_total['ok']}")
    print(f"  Skipped    : {grand_total['skipped']}")
    print(f"  Errors     : {grand_total['error']}")

    if all_errors:
        print(f"\n  ERRORS ({len(all_errors)}):")
        for e in all_errors:
            print(f"    ✗ {e}")

    print()


if __name__ == "__main__":
    main()
