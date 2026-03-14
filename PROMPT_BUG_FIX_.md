# PROMPT_BUG_FIX.md
# Reference tag: #MSMEBUFIX
# Use this prompt for: fixing a single bug, traceback, or broken behaviour
# ─────────────────────────────────────────────────────────────────────────────

---

## #MSMEPROJBRIEF
*(paste full block from AI_PROJECT_CONTEXT.md here)*
*(check the relevant zone checkbox before submitting)*

---

## Role

You are fixing a single bug in a production-style codebase.
Fix one bug only. Do not fix unrelated issues you notice along the way.

---

## Relevant Files

Only inspect these files unless you explicitly need another:

- `[file 1 — exact path e.g. backend/app/routers/jobs.py]`
- `[file 2 — exact path e.g. frontend/src/pages/Jobs.tsx]`
- `[file 3 — add only if directly involved]`

If you need a file not listed above, **name it and explain why before opening it**.

---

## Observed Error / Symptom

*(paste the exact error, traceback, console output, or symptom — no paraphrasing)*

```
[paste error here]
```

---

## Expected Behaviour

*(one or two lines — what should happen instead)*

```
[describe expected outcome]
```

---

## Constraints

- Inspect minimum context only
- Do not scan the whole repository
- Do not refactor
- Do not change unrelated code or files
- Make the smallest possible patch
- No reformatting of unrelated lines
- No renaming of files or functions unless the bug requires it

---

## Output Format

**1. Root cause** (3–5 lines max)
Explain exactly why the bug happens.

**2. Files changed**
List only files that need a patch.

**3. Patch**
Show exact before → after diff or replacement block.
If a DB migration is needed, provide the raw SQL.
If React Query cache needs updating, state which keys to invalidate.

**4. Verification**
One line: how to confirm the fix worked.
