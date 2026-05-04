# v6.3.10 — Bootstrap UI Trim functional tests

User-facing scenarios that confirm the trimmed `/employees` and `/machines`
modal forms work for real Indian MSME owners. These are MANUAL tests run
against a local `npm run dev` instance with the backend in mock mode.

Acceptance IDs are documented here so the next SRS doc-trinity pass can
fold them into Section 6.19. **Do not edit the SRS for this version**.

| AC ID      | Statement |
|-----------|-----------|
| 6.19-AC1  | Employee form requires only full_name, primary_skill, worker_type to save. |
| 6.19-AC2  | Machine form requires only name and machine_type to save. |
| 6.19-AC3  | Optional fields hidden by default behind "Add more details" expand. |
| 6.19-AC4  | Skill / machine_type list is industry-specific from `frontend/src/config/industries/{industry}.ts`. |
| 6.19-AC5  | Empty/null optional fields persist as NULL in database. |
| 6.19-AC6  | User can later edit any record to fill optional fields via the same form's expanded view. |
| 6.19-AC7  | E2E: a fresh tenant adding 7 employees + 3 machines completes in under 4 minutes. |
| 6.19-AC8  | At least 3 real-user tests confirm < 4 minute completion without external help. |

## Prep

Pick the test tenant for each industry:

- printing tenant: any new signup with `industry_type=printing`
- fabrication tenant: signup with `industry_type=fabrication`
- field_service tenant: signup with `industry_type=field_service`

For all manual tests, the WhatsApp pipeline must be in mock mode
(`WHATSAPP_MOCK_MODE=True` in backend/.env).

---

## FT-1: Fast happy path (printing tenant)

**Scenario.** Owner of a small printing shop completes onboarding from a
fresh signup. They add 5 employees and 2 machines using only required
fields. They never expand "Add more details."

**Steps.**
1. Sign up as a fresh user, choose `printing` as the industry.
2. Navigate to `/employees`. Click "Add Operator" (the industry label).
3. For each of 5 employees:
   - Type the name (e.g. "Suresh Patel").
   - Tap a skill button (Flexo Printing, Die Cutting, Lamination, Quality Control, Helper).
   - Tap "Permanent" or "Contractor".
   - Click "Add Operator". Modal closes.
4. Navigate to `/machines`. Click "Add Machine".
5. For each of 2 machines:
   - Type the name (e.g. "Press 1").
   - Tap a machine_type button (Flexo Printer, Die Cutter, Laminator, Offset Press, or Folder/Gluer).
   - Click "Add Machine".
6. Stop the timer.

**Pass criteria.**
- [ ] Total elapsed time < 3 minutes (timer reading).
- [ ] All 7 records visible in their respective tables.
- [ ] In the database, optional columns (`hourly_rate`, `overtime_rate`,
      `contact_number`, `join_date`, `department`, `location_bay`) are
      NULL for every new row created.
- [ ] Owner can navigate to `/dashboard` immediately afterwards without
      additional setup.

---

## FT-2: Mixed path (fabrication tenant filling some details)

**Scenario.** Owner adds 3 fabricators. For one (the head welder), they
expand "Add more details" and fill `hourly_rate` and `join_date`. For the
others, they leave optional fields blank.

**Steps.**
1. Sign up as a fabrication-industry user.
2. `/employees` → "Add Fabricator".
3. Add fabricator 1 (Sanjay) using minimum fields only. Save.
4. Add fabricator 2 (head welder, Raju):
   - Type name.
   - Tap "Welding" skill.
   - Tap "Permanent".
   - Click "Add more details (optional)".
   - Type 250 in Hourly Rate.
   - Pick a date in Join Date.
   - Click "Add Fabricator".
5. Add fabricator 3 (Vijay) using minimum fields only. Save.

**Pass criteria.**
- [ ] All 3 rows saved.
- [ ] Raju row has `hourly_rate=250` and `join_date=<chosen date>` in the DB.
- [ ] Sanjay and Vijay rows have those columns as NULL.
- [ ] Open Raju's row again via Edit pencil. The "Add more details" expand
      is open by default (because optional data exists). Hourly Rate shows
      "250". Verify by toggling collapse and re-expanding — the value
      stays.

---

## FT-3: Edit-later path

**Scenario.** Owner completes minimal onboarding for FT-1, then a week
later wants to add hourly rates for billing.

**Steps.**
1. Reopen the printing tenant from FT-1.
2. Navigate to `/employees`. Click the Edit pencil on row 1.
3. The form opens. The "Add more details" expand should be COLLAPSED
   (because no optional data was ever entered).
4. Click "Add more details (optional)".
5. Type 200 in Hourly Rate.
6. Click "Update Operator".
7. Open the same row again to verify.

**Pass criteria.**
- [ ] After step 6, the database row has `hourly_rate=200`. Other NULL
      columns remain NULL.
- [ ] Step 7 shows the expand auto-OPEN this time (because optional data
      now exists).

---

## FT-4: Industry-switch resilience

**Scenario.** Backend regression check — the trimmed forms behave for all
five verticals. Only need 1 fresh tenant per industry.

**Steps.** For each of `printing`, `manufacturing`, `fabrication`,
`chemical`, `field_service`:

1. Fresh signup.
2. `/employees` → "Add ___". Verify the skill button row shows the
   industry-specific labels:
   - **printing**: Flexo Printing, Die Cutting, Lamination, Quality Control, Helper
   - **manufacturing**: CNC Operation, Welding, Assembly, Quality Check, Helper
   - **fabrication**: Fabrication, Welding, Grinding, Fitting, Helper
   - **chemical**: Process Operation, Quality Control, Filling Operation, Safety Officer, Helper
   - **field_service**: HVAC, Electrical, Plumbing, Civil Works, Helper
3. `/machines` → "Add ___". Verify the machine_type button row shows
   the industry-specific labels:
   - **printing**: Flexo Printer, Die Cutter, Laminator, Offset Press, Folder/Gluer
   - **manufacturing**: CNC Lathe, Welding Station, Assembly Line, Milling Machine, Drilling Machine
   - **fabrication**: Plasma Cutter, MIG Welder, Press Brake, Bandsaw, Bench Grinder
   - **chemical**: Reactor, Mixer, Filling Line, Centrifuge, Distillation Column
   - **field_service**: Service Van, Hydraulic Lift, Diagnostic Kit, Pressure Washer, Pipe Threader
4. Tap "+ Other". Verify the row collapses to a free-text input. Type a
   custom label, click "Back to list" — the buttons reappear.

**Pass criteria.**
- [ ] Each industry shows exactly its 5 labels (no leakage across).
- [ ] "+ Other" toggle round-trips cleanly.
- [ ] Each industry's primary picker maps to a Skill row in the seeded
      tenant data — when seeded, taps result in `skills` array containing
      that skill_id; when not seeded, save still succeeds with empty
      skills list.

---

## FT-5: Mobile responsive (360px)

**Scenario.** Factory owners are mostly on phones.

**Steps.**
1. Open Chrome DevTools, switch device to "iPhone SE" (375px) or use the
   custom width 360px.
2. Open Employee form.
3. Verify: skill button row scrolls horizontally (does not wrap to multiple
   lines awkwardly). Each pill stays a single line.
4. Verify: Worker Type buttons stack as a 2-column grid that fits within
   width.
5. Open the optional expand and verify the 2-column grid degrades
   gracefully — fields should not be cut off.

**Pass criteria.**
- [ ] No horizontal page scroll, only inside the skill pill row.
- [ ] All taps reachable without zooming.

---

## Notes & deferred concerns

- **AC8** is owner-led — the Anthropic team will run 3 real factory owners
  through FT-1 and capture timings + qualitative friction notes after
  deployment.
- **Existing reports defensive null-handling**: confirmed
  `cost_service.py:53,62,150,158` already coerces `(emp.hourly_rate or 0.0)`,
  so creating employees with `hourly_rate=NULL` does not break cost reports.
  The employee is simply contributing 0 to the running cost — this matches
  the spec for not-yet-priced workers.
- The OnboardingSetup.tsx Day-1 fresh-flow already uses an even tighter
  trim; aligning Employees.tsx + Machines.tsx modals brings the two paths
  in sync.
