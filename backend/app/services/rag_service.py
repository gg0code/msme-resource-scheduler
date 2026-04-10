# rag_service.py - Version 1.0
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Manages the RAG (Retrieval-Augmented Generation) flat-file pipeline for v6.1.
# Two responsibilities:
#   1. SEEDING: When a new tenant registers, copies industry template files
#      from rag_data/_templates/{industry_type}/ into rag_data/{tenant_id}/.
#      This gives every tenant industry-relevant knowledge from Day 1.
#   2. LOADING: At query time, reads all .txt files from rag_data/{tenant_id}/
#      and returns them as a single context string for injection into the
#      AI system prompt.
#
# WHO CALLS THIS FILE
#   app/routers/auth.py  - seed_rag_from_template() called after new tenant
#                          is created in register endpoint
#   app/knowledge_graph/context_builder.py - load_rag_context() called
#                          when building the AI system prompt context block
#
# WHAT THIS FILE CALLS
#   Python stdlib: os, shutil, pathlib — no external dependencies
#
# KEY DESIGN DECISIONS
#   1. FLAT FILES MVP — v6.1 uses plain .txt files. v6.3 migrates to pgvector
#      embeddings. The folder structure here is intentionally kept stable so
#      the v6.3 migration only changes the storage layer, not the folder paths.
#   2. TENANT ISOLATION — each tenant gets their own folder: rag_data/{tenant_id}/
#      Files are NEVER read from another tenant's folder.
#   3. TENANT OVERRIDE — tenants can customise their RAG files by editing
#      rag_data/{tenant_id}/*.txt. The template is just the starting point.
#      seeding only runs once at registration — it never overwrites existing files.
#   4. SILENT DEGRADATION — if no RAG files exist for a tenant (e.g. registration
#      seeding failed, or files were accidentally deleted), load_rag_context()
#      returns an empty string. The AI still works, just without industry context.
#      We log a warning but never crash the chat pipeline.
#   5. FOLDER NOT IN GIT — rag_data/{tenant_id}/ folders are in .gitignore.
#      Only rag_data/_templates/ is committed. Tenant data is not source code.

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PATH CONSTANTS
# ---------------------------------------------------------------------------

# Base directory of the entire backend package.
# __file__ = .../backend/app/services/rag_service.py
# .parent   = .../backend/app/services/
# .parent.parent = .../backend/app/
# .parent.parent.parent = .../backend/
_BACKEND_ROOT: Path = Path(__file__).parent.parent.parent

# Where all RAG data lives — industry templates and tenant folders.
# Structure:
#   rag_data/_templates/{industry_type}/*.txt  <- committed to git
#   rag_data/{tenant_id}/*.txt                 <- NOT committed, seeded at signup
RAG_DATA_ROOT: Path = _BACKEND_ROOT / "rag_data"

# Subfolder inside RAG_DATA_ROOT that holds the industry default templates.
# These are committed to git and serve as the seed for new tenants.
TEMPLATES_DIR: Path = RAG_DATA_ROOT / "_templates"

# Valid industry types — must match Tenant.industry_type values in the DB.
# Chemical is excluded from Plan A (batch-first vertical, different entry model).
# It is in the DB as a valid value but has no RAG template in Plan A.
VALID_INDUSTRIES: frozenset[str] = frozenset({
    "printing",
    "manufacturing",
    "fabrication",
    "field_service",
})


# ---------------------------------------------------------------------------
# SEEDING — called once at tenant registration
# ---------------------------------------------------------------------------

def seed_rag_from_template(tenant_id: int, industry_type: str) -> bool:
    """
    Seed a new tenant's RAG folder from the industry template.

    Copies all .txt files from rag_data/_templates/{industry_type}/
    into rag_data/{tenant_id}/. Called once when a new tenant registers.
    Never overwrites existing files — safe to call multiple times.

    Called by:   app/routers/auth.py register endpoint, after tenant creation.
    Calls:       Python stdlib os, shutil, pathlib — no external deps.
    Args:
        tenant_id:     Integer ID of the newly created tenant.
        industry_type: Industry slug from RegisterRequest. Must be one of
                       VALID_INDUSTRIES. If unknown, logs warning and skips.
    Returns:
        True  — seeding succeeded (or files already existed, nothing to do).
        False — seeding failed (template missing or filesystem error).
                The caller should log this but NOT fail the registration.
                A tenant without RAG files still gets a working product.
    Side effects:
        Creates directory: rag_data/{tenant_id}/ if it does not exist.
        Copies .txt files from template into tenant folder.
        Writes to filesystem only — no DB writes, no network calls.
    """
    # Validate industry type — chemical excluded from Plan A templates
    if industry_type not in VALID_INDUSTRIES:
        logger.warning(
            "seed_rag_from_template: industry_type='%s' has no template "
            "(valid: %s). Skipping RAG seed for tenant %s. "
            "Tenant will work without RAG context.",
            industry_type, sorted(VALID_INDUSTRIES), tenant_id,
        )
        return False

    template_dir = TEMPLATES_DIR / industry_type
    tenant_dir = RAG_DATA_ROOT / str(tenant_id)

    # Template directory must exist — if not, it's a deployment error
    if not template_dir.exists():
        logger.error(
            "seed_rag_from_template: template directory '%s' not found. "
            "Ensure rag_data/_templates/%s/ exists in the backend directory. "
            "Tenant %s will have no RAG context until templates are added.",
            template_dir, industry_type, tenant_id,
        )
        return False

    # Create tenant folder if it does not exist yet
    try:
        tenant_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error(
            "seed_rag_from_template: could not create tenant directory '%s': %s. "
            "Check filesystem permissions on the rag_data/ folder.",
            tenant_dir, exc,
        )
        return False

    # Copy each .txt file from template to tenant folder.
    # exist_ok=True means we skip files that already exist — safe for retries.
    files_copied = 0
    files_skipped = 0

    for template_file in template_dir.glob("*.txt"):
        destination = tenant_dir / template_file.name

        if destination.exists():
            # File already exists — tenant may have customised it. Never overwrite.
            logger.debug(
                "seed_rag_from_template: '%s' already exists for tenant %s — skipping.",
                template_file.name, tenant_id,
            )
            files_skipped += 1
            continue

        try:
            shutil.copy2(template_file, destination)
            files_copied += 1
            logger.debug(
                "seed_rag_from_template: copied '%s' -> tenant %s.",
                template_file.name, tenant_id,
            )
        except OSError as exc:
            logger.error(
                "seed_rag_from_template: failed to copy '%s' for tenant %s: %s.",
                template_file.name, tenant_id, exc,
            )
            # Continue with remaining files — partial seed is better than none

    logger.info(
        "RAG seed complete for tenant %s (industry=%s): "
        "%d files copied, %d already existed.",
        tenant_id, industry_type, files_copied, files_skipped,
    )
    return True


# ---------------------------------------------------------------------------
# LOADING — called at query time to build system prompt context
# ---------------------------------------------------------------------------

def load_rag_context(tenant_id: int) -> str:
    """
    Load all RAG context files for a tenant into a single string.

    Reads every .txt file from rag_data/{tenant_id}/ and concatenates them
    with clear section headers. The result is injected into the AI system
    prompt by context_builder.py before every AI query.

    Called by:   app/knowledge_graph/context_builder.py — build_context_block()
    Calls:       Python stdlib pathlib — no external deps, no DB calls.
    Args:
        tenant_id: Integer ID of the tenant to load context for.
    Returns:
        Single string containing all RAG file contents with section headers.
        Returns empty string "" if no files exist — caller handles gracefully.
        Never raises — all errors are caught and logged.
    Side effects:
        Read-only filesystem access. No writes, no DB, no network.
    """
    tenant_dir = RAG_DATA_ROOT / str(tenant_id)

    # If tenant folder does not exist, return empty — no RAG context available.
    # This happens for tenants registered before v6.1 or if seeding failed.
    if not tenant_dir.exists():
        logger.warning(
            "load_rag_context: no RAG folder found for tenant %s at '%s'. "
            "AI will answer without industry context. "
            "Run seed_rag_from_template(%s, industry_type) to fix this.",
            tenant_id, tenant_dir, tenant_id,
        )
        return ""

    txt_files = sorted(tenant_dir.glob("*.txt"))

    if not txt_files:
        logger.warning(
            "load_rag_context: tenant %s has a RAG folder but no .txt files. "
            "Check that seeding ran correctly.",
            tenant_id,
        )
        return ""

    # Build context string — one section per file with clear headers
    # so the AI knows which file each piece of knowledge came from.
    sections: list[str] = []

    for txt_file in txt_files:
        try:
            content = txt_file.read_text(encoding="utf-8").strip()
            if not content:
                continue  # Skip empty files silently

            # Use the filename (without .txt) as the section header.
            # e.g. "paper_rates.txt" -> "INDUSTRY KNOWLEDGE: paper_rates"
            section_name = txt_file.stem.upper().replace("_", " ")
            sections.append(
                f"--- INDUSTRY KNOWLEDGE: {section_name} ---\n{content}"
            )

        except OSError as exc:
            # Log and skip — don't let one bad file break the whole context
            logger.error(
                "load_rag_context: could not read '%s' for tenant %s: %s.",
                txt_file.name, tenant_id, exc,
            )

    if not sections:
        return ""

    # Join all sections with double newline separators for readability
    rag_block = "\n\n".join(sections)

    logger.debug(
        "load_rag_context: loaded %d RAG files for tenant %s (%d chars total).",
        len(sections), tenant_id, len(rag_block),
    )

    return rag_block


# ---------------------------------------------------------------------------
# UTILITY — for admin / debugging use only
# ---------------------------------------------------------------------------

def list_tenant_rag_files(tenant_id: int) -> list[str]:
    """
    List all RAG files currently seeded for a tenant.

    Utility function for debugging and admin tooling only.
    Not called in the normal request path.

    Called by:   dev scripts, admin endpoints (future)
    Calls:       pathlib — no external deps
    Args:
        tenant_id: Integer ID of the tenant.
    Returns:
        List of filename strings e.g. ["paper_rates.txt", "machine_specs.txt"]
        Empty list if folder does not exist or has no .txt files.
    Side effects: None — read-only
    """
    tenant_dir = RAG_DATA_ROOT / str(tenant_id)
    if not tenant_dir.exists():
        return []
    return sorted(f.name for f in tenant_dir.glob("*.txt"))
