# PROMPT_FEATURE_ADD.md
# Reference tag: #MSMEFEATURE
# Use this prompt for: adding one new capability with strict scope control
# ─────────────────────────────────────────────────────────────────────────────

---

## #MSMEPROJBRIEF
*(paste full block from AI_PROJECT_CONTEXT.md here)*
*(check the relevant zone checkbox before submitting)*

---

## Role

You are adding one feature to an existing production codebase.
Add one feature only. Do not improve, refactor, or extend anything else you notice.

---

## Feature to Add

*(describe one feature only — one paragraph max)*

```
[describe the feature here]
```

---

## Business Rules / Expected Behaviour

*(what the feature must do — be explicit, edge cases included)*

- [ ] Rule 1: `[e.g. Only proprietor and scheduler roles can access this]`
- [ ] Rule 2: `[e.g. All DB queries must be tenant-scoped]`
- [ ] Rule 3: `[e.g. If no data exists, show empty state — not an error]`
- [ ] Rule 4: `[add as many as needed]`

---

## Relevant Files

Only inspect and edit these files unless you explicitly need another:

- `[file 1 — exact path e.g. backend/app/routers/jobs.py]`
- `[file 2 — exact path e.g. frontend/src/pages/Jobs.tsx]`
- `[file 3 — add only if directly involved]`

If you need a file not listed, **name it and explain why before opening it**.

---

## Out of Scope

**Confirm these are NOT part of this feature before proceeding:**

- [ ] `[thing 1 — e.g. Do not change the auto-scheduler logic]`
- [ ] `[thing 2 — e.g. Do not modify existing API response shapes]`
- [ ] `[thing 3 — e.g. Do not add new navigation items to Layout.tsx]`

> ⚠️ If any out-of-scope item turns out to be required, **stop and ask** before proceeding.

---

## Constraints

- Inspect minimum context only
- Do not redesign architecture
- Reuse existing patterns (same auth pattern, same query key conventions, same Tailwind style)
- Create only the files needed for this feature
- Avoid touching unrelated modules
- No reformatting of unrelated code
- Tenant-scoped on every new DB query — no exceptions
- New DB columns must be nullable or have a default

---

## Output Format

**1. Implementation plan** (5–8 lines)
Summarise what will be built, which files touched, and in what order.

**2. Schema / API contract changes** *(if any)*
State any new endpoints, request/response shapes, or DB columns
before writing any code.

**3. DB migration** *(if needed)*
Raw SQL only — no Alembic.

**4. Backend patch**
Exact code additions / replacements.

**5. Frontend patch**
Exact code additions / replacements.
State which React Query keys are invalidated.

**6. Out-of-scope confirmation**
One line per item confirming each out-of-scope thing was not touched.

**7. Test steps**
3–5 manual steps to verify the feature works end-to-end.
