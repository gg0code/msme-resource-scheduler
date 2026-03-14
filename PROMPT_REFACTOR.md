# PROMPT_REFACTOR.md
# Reference tag: #MSMEREFACTOR
# Use this prompt for: improving code clarity zone by zone, comments, readability
# ─────────────────────────────────────────────────────────────────────────────

---

## #MSMEPROJBRIEF
*(paste full block from AI_PROJECT_CONTEXT.md here)*
*(check the relevant zone checkbox before submitting)*

---

## Role

You are refactoring a limited part of a production codebase for clarity only.
Do not change any behaviour. Do not touch any zone not listed in this prompt.

---

## Application Zones

This codebase has 6 defined zones. Work one zone per prompt run.

| # | Zone | Key Files |
|---|---|---|
| 1 | **Backend — Core** | `routers/jobs.py`, `routers/employees.py`, `routers/machines.py`, `routers/assignments.py` |
| 2 | **Backend — Scheduler** | `routers/scheduler_router.py`, `routers/jobs.py` (auto-schedule section only) |
| 3 | **Backend — Auth / Scan** | `routers/auth.py`, `routers/scan.py`, `services/token_service.py` |
| 4 | **Frontend — Pages** | `pages/Jobs.tsx`, `pages/Employees.tsx`, `pages/Machines.tsx`, `pages/GanttPage.tsx` |
| 5 | **Frontend — Scheduler UI** | `scheduler/useScheduler.ts`, `scheduler/SchedulerContext.tsx`, `scheduler/SchedulerToolbar.tsx` |
| 6 | **AI Copilot** | `routers/ai_chat.py`, `components/AICopilot.tsx` |

---

## Refactoring Goal

**Zone selected:** `[enter zone number and name — e.g. Zone 1 — Backend Core]`

**Goal:** Improve code clarity and add documentation comments so that a developer
with moderate skill can read, understand, and safely modify the code.

---

## What To Do — Per File in the Selected Zone

For **each file** in the zone:

1. **File-level comment block** — add or update a comment at the top:
   ```
   Purpose: what this file does in one sentence
   Owned by: [zone name]
   Key dependencies: [list 2-3 files it imports from]
   Tenant-scoped: yes / no
   ```

2. **Function-level comments** — above each function/endpoint add:
   ```
   # What this function does (1 line)
   # Inputs: [key params]
   # Returns: [what it returns or mutates]
   # Side effects: [DB writes, cache invalidations, external calls — or "none"]
   ```

3. **Inline clarity** — where logic is non-obvious:
   - Add a short inline comment explaining *why*, not *what*
   - Extract a magic number or string into a named constant if it appears more than once
   - Break a long condition into a named boolean variable if it improves readability

4. **Simplify only if safe** — if a block is overly complex:
   - Flatten unnecessary nesting (early return pattern)
   - Remove dead code (unused imports, commented-out blocks)
   - Split a function longer than ~60 lines only if the split is obvious and named clearly

---

## Do Not Change

- External behaviour of any function
- API response shapes (field names, types, status codes)
- Database schema (no new columns, no renames)
- Function names, class names, or variable names used outside these files
- React Query key strings
- Tailwind class strings (frontend)
- Any logic that could silently alter output

---

## Constraints

- One zone per prompt run — do not spill into other zones
- No repo-wide formatting passes
- No architectural redesign
- No new abstractions unless they replace 3+ identical blocks
- Prefer local cleanup only
- Backend: do not alter SQLAlchemy query structure unless purely cosmetic
- Frontend: do not change component props, hook return shapes, or event handlers

---

## Output Format

**1. Code smells found** (bullet list, brief)
List what you noticed — unclear names, missing comments, long functions, magic values, etc.

**2. Refactor plan** (5 lines max)
What you will change and why. Confirm nothing functional is touched.

**3. Updated files**
One file at a time. Show the complete updated file (not just a diff)
so it can be copied directly into the project.

**4. Change summary**
For each file: list exactly what was added/changed (comments, constants, extractions).
Confirm: *"No logic, API responses, DB schema, or external names were changed."*
