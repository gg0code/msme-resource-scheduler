# v6.3.11 — Pattern-Aware Briefing Intelligence: Signal Specification

**Status.** Design only. No code, no migration, no model edits. Once you
review and answer the open questions in Section G, Session 2 will
implement against the spec you sign off on.

**Version target.** v6.3.11 (next minor after v6.3.10 — Bootstrap UI Trim).

**Scope boundary.** This document specifies the *content* of daily push
briefings. The *cadence* (when), *channel* (WhatsApp), *recipients*
(top-tier subscribed users), and *transport* (the v6.3.4 dispatcher)
are unchanged. Only `_build_content_for_kind()` in
`backend/app/services/briefings/dispatcher.py` gets a new path.

---

## Section A — Data inventory

Reference tenant: tenant_id = 12 (printing-industry demo seed).
Counts captured 2026-05-04.

### A.1 — `employees`

| Column | Type | Notes |
|---|---|---|
| id, tenant_id, full_name | int / int / str(150) | core |
| status | str(20) NOT NULL | **CURRENT snapshot only**. Mixed casing — see Section C |
| worker_type | str(20) NOT NULL | 'permanent' \| 'contractor' (lowercase, v5.16) |
| source | str(20) NOT NULL | 'manual' \| 'whatsapp' \| 'erp_sync' (v5.16) |
| department, gender, date_of_birth, contact_number, employment_type, base_availability_pct, join_date, hourly_rate, overtime_rate | various, nullable | descriptive |
| created_at, updated_at | DateTime | row creation + last edit |

Tenant 12 has **11 employees** (prompt said 12; close enough — the demo
seeder creates 11–12 depending on industry path).

**Critical gap.** `employees.status` is a snapshot. There is **no
historical attendance**. "Suresh was absent yesterday" cannot be
recovered from this table — only "Suresh's status RIGHT NOW is `absent`".

### A.2 — `machines`

| Column | Type | Notes |
|---|---|---|
| id, tenant_id, name, machine_type | int / int / str / str | core |
| status | str(30) NOT NULL | 'Operational' \| 'active' \| 'Under Maintenance' — see Section C |
| source | str(20) | 'manual' \| 'whatsapp' \| 'erp_sync' |
| base_availability_pct, location_bay, hourly_rate | nullable descriptive | |
| created_at, updated_at | DateTime | |

Tenant 12: **8 machines**.

Same gap as employees: only current snapshot of status. No history.

### A.3 — `jobs`

| Column | Type | Notes |
|---|---|---|
| id, tenant_id, name, customer | int / int / str / str | core |
| start_date, end_date | Date | scheduled window |
| status | str(30) NOT NULL default 'Draft' | 8 distinct values across all tenants — see Section C |
| priority | str(20) | 'Critical' / 'High' / 'Medium' / 'Low' |
| timer_status, actual_start_at, actual_end_at, paused_seconds, timer_log | varied | runtime tracking |
| order_value, tentative_profit | Float, nullable | revenue |
| original_start_date, original_end_date | Date, nullable | non-null = scheduler moved this job |
| created_at, updated_at | DateTime | |

Tenant 12: **9 jobs**.

**Critical gap.** `actual_start_at` is **mostly NULL** even when
`status = 'in_progress'`. In tenant 12, only the one `Completed` job
(id=65) has `actual_start_at` populated. Eight other jobs (mix of
`pending` / `in_progress` / `Scheduled` / `Pending Assignment` /
`Draft`) all show `actual_start_at = None`. So a "no progress in N days"
signal cannot rely on `actual_start_at` — use `updated_at` instead, with
the caveat that any manual edit to the job (priority change, etc.)
refreshes `updated_at` regardless of progress.

### A.4 — `events` (audit table from migration 028)

| Column | Type | Notes |
|---|---|---|
| id, tenant_id | int | indexed |
| event_type | str(50) | dotted-string discriminator, indexed |
| entity_type, entity_id | str(50) / int? | polymorphic pointer (no FK on entity_id) |
| actor_user_id | int? | NULL for system-generated events |
| source | str(20) | 'web' \| 'whatsapp' \| 'system' |
| payload | JSONB | event-specific |
| created_at | timestamptz, server_default now() | append-only |

**Distribution across all tenants** (38 rows total, 17 in tenant 12):

```
user.invited                14
briefing.manual_trigger      7
briefing.sent                7
member.invited_whatsapp      6
user.deactivated             4
```

By entity_type: `user` (24), `briefing` (14).

**Gap.** No `employee.absent`, `machine.status_changed`, `job.delayed`,
or any other operational event types yet. The events table today is
purely a role-management + briefing audit log. To detect attendance
patterns, **either** the manager check-in flow needs to start writing
attendance events here going forward, **or** signals must read from
elsewhere (Redis check-in / employee_leaves / whatsapp_conversations).

### A.5 — `employee_leaves`, `machine_downtimes`, `availability_overrides`

These DO exist as date-range historical ledgers. Schemas:

`employee_leaves`: id, tenant_id, employee_id, **start_date**, **end_date**, reason, created_at.
`machine_downtimes`: id, tenant_id, machine_id, **start_date**, **end_date**, reason, created_at.
`availability_overrides`: id, tenant_id, employee_id?, machine_id?, **date_from**, **date_to**, availability_pct, reason, created_at.

**Real-world utilisation right now (across ALL tenants):**

```
employee_leaves         1 row total
machine_downtimes       1 row total
availability_overrides  0 rows
```

Tenant 12 has zero rows in any of the three. **These tables are
nominally available but practically empty** in the current dataset.
Signals based on them will rarely fire until owners start using the
desktop UI to record planned leaves and downtime — or until the
WhatsApp pipeline starts auto-creating these rows from inbound messages
(deferred to v6.3.13–15 entity extraction).

### A.6 — `phone_tenant_map`, `whatsapp_conversations`

`phone_tenant_map`: 21 rows total, 3 in tenant 12. Key columns:
`phone_number` (E.164), `tenant_id`, `user_id`, `is_active`,
`consent_given`, `last_seen_at`. `last_seen_at` is the only operational
freshness signal — could feed a "no manager touch in N days" health
flag.

`whatsapp_conversations`: 34 rows total (24 in tenant 12). One row per
inbound or outbound message. `role`, `content`, `language`,
`session_id`, `consent_given`, `created_at`. The raw text contains
attendance / issue mentions ("Suresh aaj nahi aaya") but **mining it is
out of scope** for v6.3.11 — that is the v6.3.13–15 entity extraction
deliverable.

### A.7 — Manager check-in (Redis only, NOT in DB)

`backend/app/services/whatsapp_checkin.py:save_checkin_state()` writes
to Redis under key `whatsapp:checkin:{tenant_id}:{date}` with **24-hour
TTL**. Payload:

```
{ "absent_ids": [int, ...],
  "down_machine_ids": [int, ...],
  "recorded_at": "<iso>" }
```

The structure exists. The history doesn't — it expires after 24 hours.

**This is the biggest gap.** The manager already tells the bot every
morning who's absent and which machines are down. Today that data
evaporates 24 hours later. To detect "Suresh absent 2 days in a row"
the dispatcher needs *historical* check-in data. Three ways to get it:

  1. **Persist check-in writes to a new DB table going forward.**
     Requires a small additive migration (out of scope per the v6.3.11
     constraint "no migrations") OR add an `attendance.recorded` event
     to the existing `events` table on every check-in (no migration —
     events table already accepts arbitrary `event_type` strings).
  2. **Cross-reference `employee_leaves`.** Picks up planned absences
     but misses unplanned no-shows. Today's data shows this is a near-
     empty table.
  3. **Defer to v6.3.13–15** (entity extraction from
     `whatsapp_conversations`).

**Strong recommendation, surfaced to the user as Q1 in Section G:**
treat option 1 with the events-table approach as a v6.3.11 prerequisite.
It is one line of code (`db.add(Event(event_type='attendance.recorded',
...))`) added to the existing `save_checkin_state()` call site. No
migration. No new table. Once it's wired, signals can read 7+ days of
attendance from `events`.

---

## Section B — Signal catalog

Each signal below follows the schema in the prompt. Signals marked with
**[BLOCKED]** cannot fire until a data prerequisite is resolved (call
out in Section G); they are still spec'd because the user may resolve
the prerequisite as part of v6.3.11.

### B.1 — Attendance signals

#### Signal: `consecutive_absence` **[BLOCKED on attendance history]**

- **Description.** Employee X has been marked absent on 2+ consecutive
  working days.
- **Trigger condition.** For each employee where `worker_type = 'permanent'`,
  count working-day check-ins in the last 7 days where `employee.id ∈
  absent_ids`. If the count is 2+ AND the most-recent absence is today
  AND the prior absence is the previous working day, fire.
- **Data source.** `events` table (after attendance events are wired) OR
  `employee_leaves` (today, near-empty).
- **Window.** 7 working days lookback.
- **Threshold.** 2 consecutive working days (configurable; user may
  prefer 3).
- **Suppression.**
  - Skip contractors (worker_type = 'contractor') — variable presence
    is the deal.
  - Skip employees with `created_at` within last 7 days (new joinees).
  - Skip if there's an `employee_leaves` row covering the dates (planned
    leave, owner already knows).
- **Output template.**
  - Day 2: "{name} pichhle 2 din se nahi aaye"
  - Day 3+: "{name} ab tak {N} din se gayab — kuch baat hai?"
- **Confidence.** High (once data prerequisite is met).
- **Priority tier.** **1 — must fire** when triggered. Owners care most
  about workforce reliability.

#### Signal: `attendance_ratio_concern` **[BLOCKED]**

- **Description.** Employee's attendance over the last N working days is
  below threshold.
- **Trigger condition.** For each permanent employee with ≥ 7 working
  days of history, compute `present_days / working_days`. If `< 0.6`,
  fire. (Sub-threshold is meaningfully below normal — most permanent
  workers should be 0.85+.)
- **Data source.** `events` (after attendance events wired).
- **Window.** Last 14 working days (rolling).
- **Threshold.** ratio < 0.6. User may want industry-specific.
- **Suppression.**
  - Need at least 7 working days of history (skip new joinees).
  - Skip if `consecutive_absence` is already firing for this employee
    today (don't double-message).
  - Cooldown: only fire once per employee per 7-day window.
- **Output template.**
  - "Pichhle 2 hafte mein {name} sirf {pct}% present rahe — sab theek hai?"
- **Confidence.** Medium (depends on check-in compliance — if manager
  doesn't reply some days, ratio is biased).
- **Priority tier.** 2.

#### Signal: `new_employee_no_show`

- **Description.** Recently added employee has never been marked
  active/present after onboarding.
- **Trigger condition.** Employee created in last 14 days where
  `employee.status` is still `absent` OR no check-in event mentions them
  AND their `created_at + 3 working days < today`.
- **Data source.** `employees`, `events`.
- **Window.** N/A (single-shot).
- **Threshold.** 3 working days post-creation with no presence signal.
- **Suppression.**
  - Skip if there's a future-dated `employee_leaves` row (joining late
    deliberately).
  - Cooldown: fire once per employee, never twice.
- **Output template.**
  - "{name} ko aapne {N} din pehle add kiya — kya woh aaye nahi abhi
    tak?"
- **Confidence.** Medium.
- **Priority tier.** 2.

### B.2 — Machine signals

#### Signal: `idle_machine`

- **Description.** Machine has had no job assignment for N working days.
- **Trigger condition.** For each machine with status NOT IN
  ('Under Maintenance', 'Decommissioned'), find the most recent
  `job_assignments.assigned_at` (or any related job whose date range
  overlapped the machine in the last N days). If none in last 7 working
  days, fire.
- **Data source.** `machines`, `job_assignments`, `jobs`.
- **Window.** 7 working days.
- **Threshold.** zero assignments in window.
- **Suppression.**
  - Skip if machine has open `machine_downtimes` row (owner knows it's
    out).
  - Skip in tenant's first 14 days (insufficient activity baseline).
  - Cooldown: 7 days — same idle machine doesn't repeat-fire daily.
- **Output template.**
  - "{machine_name} ek hafte se khali hai — koi {job_label} dena hai?"
- **Confidence.** High.
- **Priority tier.** 2.

#### Signal: `low_utilization`

- **Description.** Machine assigned to jobs whose total scheduled
  duration in the last 7 working days is less than `threshold_pct` of
  available hours.
- **Trigger condition.** Compute machine usage % from overlapping
  job_assignments. Fire when < 30%. (Many small shops are bursty so
  threshold needs tuning — see Q3.)
- **Data source.** `jobs.start_date`, `jobs.end_date`,
  `jobs.estimated_hours_per_day`, `job_assignments`.
- **Window.** 7 working days.
- **Threshold.** utilisation < 30% (DEFAULT — see Q3).
- **Suppression.** Same as `idle_machine` plus: skip if `idle_machine`
  is already firing for this machine.
- **Output template.**
  - "{machine_name} pichhle hafte sirf {pct}% busy thi."
- **Confidence.** Medium (job-day math is approximate).
- **Priority tier.** 3 (experimental — turn off if it's noisy in pilot).

#### Signal: `status_change_alert`

- **Description.** Machine flipped from Operational → non-Operational in
  the last 24 hours and the owner hasn't acknowledged yet.
- **Trigger condition.** Need a machine status-change event log. Today's
  `events` table doesn't capture it. Detect via
  `machines.updated_at >= today - 1 day AND status NOT IN
  ('Operational', 'active')`.
- **Data source.** `machines`.
- **Window.** Last 24 hours.
- **Threshold.** any flip to non-Operational.
- **Suppression.** Skip if the change came from a WhatsApp action by
  the same owner who'd receive the briefing.
- **Output template.**
  - "{machine_name} ka status kal raat 'Under Maintenance' hua. Kab tak
    theek ho jaayegi?"
- **Confidence.** Low — `updated_at` refreshes on any column change, not
  just status flips. Fix would need a `machine.status_changed` event
  log.
- **Priority tier.** 3.

### B.3 — Job signals

#### Signal: `delayed_jobs_count`

- **Description.** N jobs whose `end_date < today` are still not in a
  terminal status.
- **Trigger condition.** Already implemented as a *count* in
  `morning_content._delayed_job_count()`. v6.3.11 promotes it to a
  *signal* with names attached: when the delayed list is non-empty AND
  small enough to enumerate (≤ 3 jobs), surface job names. When > 3,
  fall back to count-only summary.
- **Data source.** `jobs`.
- **Window.** N/A — point-in-time check.
- **Threshold.** ≥ 1 delayed job.
- **Suppression.** Cooldown: don't repeat the same job names 2 days in
  a row unless a new job entered the delayed list.
- **Output template.**
  - 1 job:  "{job_name} kal end hone wala tha, abhi tak chal raha hai."
  - 2-3:    "{job1}, {job2} aur {job3} sab delayed hai."
  - 4+:     "{N} {job_label} ab tak end nahi hue."
- **Confidence.** High.
- **Priority tier.** 1.

#### Signal: `conflict_jobs_count`

- **Description.** N jobs flagged with scheduling conflicts.
- **Trigger condition.** `jobs.has_conflict = TRUE` (or whatever the
  flag is — needs grep). NOTE: I did not verify a `has_conflict` column
  exists on `jobs`. Section A.3 schema does NOT show one. **The "8
  conflicts detected" string the user pasted comes from somewhere else
  and needs a follow-up grep.** Q4 in Section G.
- **Data source.** TBD pending grep.
- **Confidence.** **CANNOT SHIP** until source is identified.
- **Priority tier.** 1 (assuming source exists and is reliable).

#### Signal: `no_progress`

- **Description.** Job in `in_progress` status whose `actual_start_at`
  is NULL OR whose `updated_at < today - N days`.
- **Trigger condition.** `status` IN ('in_progress', 'In Progress') AND
  (`actual_start_at IS NULL` AND `updated_at < today - 3`).
- **Data source.** `jobs`.
- **Window.** Last 3 days.
- **Threshold.** 3 days.
- **Suppression.** Skip if job is locked (`is_locked = TRUE`) — owner
  pinned it deliberately. Cooldown: 3 days.
- **Output template.**
  - "{job_name} 3 din se in-progress hai par koi update nahi mila."
- **Confidence.** Medium-Low. As Section A.3 documented, `actual_start_at`
  is mostly NULL because the timer feature is rarely used. Many "real"
  in-progress jobs would falsely trigger this.
- **Priority tier.** 3 (until timer adoption is verified).

### B.4 — Customer / pattern signals

#### Signal: `recurring_customer_callout`

- **Description.** A customer name appears in 3+ jobs in the last 30 days
  — call out that this is a top-tier customer worth flagging.
- **Trigger condition.** GROUP BY `jobs.customer` over last 30 days,
  filter `count >= 3` AND status NOT IN terminal states.
- **Data source.** `jobs.customer`, `jobs.status`, `jobs.created_at`.
- **Window.** 30 days.
- **Threshold.** ≥ 3 jobs from one customer.
- **Suppression.** Show this only on Day-7 / Day-30 markers — daily
  noise otherwise.
- **Output template.**
  - "{customer} ke saath aapke {N} {job_label} chal rahe hai — top
    customer."
- **Confidence.** High.
- **Priority tier.** 2 (high-quality observation; demonstrates the bot
  is "listening").

#### Signal: `revenue_at_risk`

- **Description.** Sum of `order_value` for delayed jobs.
- **Trigger condition.** SUM(jobs.order_value) WHERE delayed = true AND
  order_value IS NOT NULL. Fire when sum > some threshold (e.g.,
  ₹50,000) or when 3+ delayed jobs combined have any order_value.
- **Data source.** `jobs.order_value`, derived delayed flag.
- **Window.** Point-in-time.
- **Threshold.** ₹50,000 (configurable; depends on tenant size — see
  Q5).
- **Suppression.** Skip when `delayed_jobs_count` is already firing for
  the same set of jobs (avoid double-message). Surface on alternate
  days.
- **Output template.**
  - "{N} delayed jobs ka total ₹{amount} order value pending hai."
- **Confidence.** Medium. `order_value` is nullable and not always
  populated (per Section A.3).
- **Priority tier.** 2.

### B.5 — Day-of-tenancy signals

#### Signal: `day_2_first_observation`

- **Description.** On the second working day after tenant signup, send
  one early observation that proves the bot was watching from Day 1.
- **Trigger condition.** Today is the tenant's 2nd working day OR
  tenant.created_at is exactly 1 working day ago. Pick the
  highest-confidence signal from Section B that has fired today; if
  none, fall back to a "first impression" template that lists what was
  added (e.g. "I see {N} {employees_label} and {M} {machines_label}").
- **Data source.** Tenant, plus whatever signal qualified.
- **Window.** Single-shot.
- **Suppression.** Fires exactly once.
- **Output template.**
  - "Yesterday aapne {N} {employees_label} aur {M} {machines_label}
    add kiye. Aaj se main rozana plan dekh raha hoon."
- **Confidence.** High.
- **Priority tier.** 1 (must fire — first-impression moment).

#### Signal: `day_7_wow_signal`

- **Description.** On the 7th working day, surface the strongest
  pattern detected in the listening week.
- **Trigger condition.** Day count == 7. Pick the signal with highest
  confidence that fired on at least 3 of the last 7 days. Examples:
  "Suresh kabhi-kabhi miss karte hai", "Machine 2 lagatar idle hai",
  "Cipla aapka top customer ban gaya".
- **Note.** The Day-7 wow gate is its own selection layer (deferred to
  v6.3.16 per the prompt). v6.3.11 produces *daily* signals; the Day-7
  composer wraps them.
- **Confidence.** Medium (depends on a week of data).
- **Priority tier.** 1 on day 7.

#### Signal: `day_30_savings_receipt`

- **Description.** On the 30th day, surface a measured savings number.
- **Trigger condition.** Day count == 30 AND the v6.24 KPI Baseline
  module exists.
- **Note.** **Dependency on v6.24 KPI Baseline + Monthly Savings
  Summary, which is not yet shipped.** Spec line is here so the user
  knows v6.3.11 leaves a placeholder. No signal evaluator in v6.3.11.

### B.6 — Health / freshness signals

#### Signal: `manager_silence`

- **Description.** Manager hasn't replied to morning check-in in N
  consecutive working days.
- **Trigger condition.** For each tenant with check-in enabled, look at
  Redis history (or persisted attendance events) to count working days
  with no check-in reply. Fire at N=3.
- **Data source.** `events` (after attendance events wired) OR direct
  Redis scan.
- **Window.** Last 7 working days.
- **Threshold.** 3 consecutive missed check-ins.
- **Suppression.** Cooldown: same signal once per 7 days.
- **Output template.**
  - "Pichhle 3 din se manager check-in reply nahi mila — sab theek hai?"
- **Confidence.** High once data is wired.
- **Priority tier.** 2.

---

## Section C — Status field reality check

Distinct values found in the production-like data:

### `employees.status`

```
'Active'      171  ← title-case dominant
'Inactive'      4
'active'        4  ← lowercase from manager check-in flow
'absent'        1  ← lowercase, from check-in
'On Leave'      1
```

### `machines.status`

```
'Operational'         99  ← title-case dominant
'Under Maintenance'    4
'active'               5  ← outlier (probably set via WhatsApp action)
```

### `jobs.status`

```
'Draft'                57
'Scheduled'            30
'Pending Assignment'   22
'Completed'             8
'pending'               3  ← lowercase variant
'In Progress'           3
'in_progress'           2  ← lowercase variant
'Stopped'               1
```

### Per-signal mapping

| Signal | Treats as positive | Treats as negative | Ambiguous |
|---|---|---|---|
| consecutive_absence | n/a (signal computes from events, not status) | `'absent'` | — |
| idle_machine | `('Operational','active')` | `('Under Maintenance','Decommissioned')` | — |
| status_change_alert | n/a (looks at recent flip) | `('Under Maintenance','Decommissioned')` | — |
| delayed_jobs_count | terminal: `('Completed','completed','Cancelled','cancelled')` | non-terminal: everything else | `'Stopped'` (1 row) — terminal-ish but not in current code |
| no_progress | `('in_progress','In Progress')` is the trigger universe | terminal blocks | the title-case mismatch is the bug |

### Recommendation — surfaced for user decision (Q6)

**Option (a): A normalisation migration in v6.3.11.**

Pros: clean state going forward, signals don't need lowercase-tolerant
WHERE clauses, fewer if-statements scattered through future code.

Cons: requires a new migration `029` (the prompt says no migrations for
v6.3.11), backfill needs to be tested across both Postgres and the
SQLite test path, and the migration is irreversible without per-row
forensics.

**Option (b): Application-level case-insensitive comparison.**

Pros: zero migration risk, ships in v6.3.11 without expanding scope,
matches what the existing briefing code already does (e.g.
`Job.status.notin_(['completed','Completed','cancelled','Cancelled'])`).

Cons: technical debt, every new query must remember the variants, easy
to forget one and silently miss rows.

**My recommendation: (b) for v6.3.11**, with a separate v6.4.x ticket
for the normalisation migration once the signal evaluators ship and we
confirm the variants don't expand further. Keeping v6.3.11 contained is
worth the small debt. If the user disagrees, surface as Q6.

---

## Section D — Briefing message composition rules

The composer runs once per dispatch (per tenant, per kind = morning or
evening). It produces a single string that the existing dispatcher
sends.

### D.1 — Maximum signals per briefing

**Recommendation: 1 to 3 signals per briefing, hard cap at 3.**

Single-signal briefings are the sweet spot for "earned attention" — the
moment you list five things, you've recreated the templated noise the
prompt is trying to escape. Three is the absolute maximum, and only
when the signals are diverse (see D.3).

The existing morning briefing keeps a 1000-character cap (per SRS
6.28.4); each signal contributes ~80–120 characters, so 3 signals plus
the header still fits.

### D.2 — Selection priority

1. **Tier 1 always wins.** If any tier-1 signal fires today
   (`consecutive_absence`, `delayed_jobs_count`, `day_2`, `day_7`),
   include it.
2. **Then highest-confidence tier-2.** Sort tier-2 signals by
   confidence (high > medium > low) and recency.
3. **Tier 3 only if slots remain.** Tier 3 is experimental — fire only
   when zero tier-1 / tier-2 signals qualify.
4. **Tie-break: most-recent change wins.** Two equal-tier signals →
   pick the one whose underlying data changed most recently.

### D.3 — Diversity rule

If the top 3 candidates are all from the same category (e.g., three
attendance signals), keep the highest-priority one and pick the next
non-attendance signal for slot 2. This prevents "Suresh, Anil, Mohan
all absent" cascading into a wall of attendance bullets.

Categories:
- attendance (B.1)
- machine (B.2)
- job (B.3)
- customer (B.4)
- day-of-tenancy (B.5)
- health (B.6)

### D.4 — Cooldown rule

Each signal has a `cooldown_days` setting (declared per-signal in B).
The composer tracks "last fired at" via a new key in the existing
`events` table:

```
event_type='briefing.signal_fired'
payload={'signal_id': 'consecutive_absence', 'subject_entity_id': 7,
         'message': '<text>'}
```

Before firing, check if the same `(signal_id, subject_entity_id)` has
fired within `cooldown_days`. If yes, skip — *unless* the signal
escalates (D.5).

### D.5 — Escalation rule

If a signal has fired before for the same subject AND the underlying
fact has materially worsened, fire again with an escalated message even
inside the cooldown window:

```
day 1:  "Suresh kal nahi aaye"
day 2:  "Suresh 2 din se nahi aaye"          ← escalation; cooldown bypassed
day 3:  "Suresh ab tak 3 din se gayab"       ← escalation; cooldown bypassed
day 4-9: cooldown holds; no message
day 10: if pattern continues → "Suresh is hafte 60% present"
        (different signal: attendance_ratio_concern)
```

The composer compares the prior payload to the new one. If a numeric
threshold has crossed (2 → 3 days, or new entity has joined the delayed
list), it's an escalation.

### D.6 — Idle case

When zero signals qualify after all selection + diversity + cooldown
rules, the briefing falls back to the **existing v6.3.4 templated
output** (count of jobs, count of employees, top job for tomorrow).

This is intentional. Inventing pseudo-observations on quiet days erodes
trust faster than templated content does.

The fallback message gets a trailing one-liner: "Aaj koi alag pattern
nahi dikha — sab routine hai." Owners learn that a quiet briefing means
the bot is paying attention but has nothing material to flag.

---

## Section E — Implementation sketch (no code)

### E.1 — Module layout

```
backend/app/services/briefing_intelligence/
    __init__.py             — public surface
    signals.py              — Signal dataclass + SignalResult
    catalog/
        attendance.py       — detect_consecutive_absence(),
                              detect_attendance_ratio_concern(),
                              detect_new_employee_no_show()
        machine.py          — detect_idle_machine(),
                              detect_low_utilization(),
                              detect_status_change_alert()
        job.py              — detect_delayed_jobs(),
                              detect_conflict_jobs(),
                              detect_no_progress()
        customer.py         — detect_recurring_customer(),
                              detect_revenue_at_risk()
        tenancy.py          — detect_day_2(), detect_day_7()
        health.py           — detect_manager_silence()
    composer.py             — compose_briefing(tenant_id, day_count, db)
                              -> BriefingContent
    cooldown.py             — read/write briefing.signal_fired events
                              for cooldown + escalation tracking
```

### E.2 — Signal contract

Each evaluator signature:

```python
def detect_<name>(tenant_id: int, today: date, db: Session)
    -> Optional[SignalResult]
```

`SignalResult` dataclass:

```python
@dataclass
class SignalResult:
    signal_id: str               # 'consecutive_absence'
    category: str                # 'attendance' | 'machine' | ...
    tier: int                    # 1, 2, 3
    confidence: str              # 'high', 'medium', 'low'
    subject_entity_type: str     # 'employee' | 'machine' | 'job' | ...
    subject_entity_id: Optional[int]
    severity_score: float        # used for escalation comparison
    message_hi_en: str
    message_en: str
    cooldown_days: int
    suppression_reasons: list[str]  # populated when not fired (debug)
```

`None` means "did not fire". Evaluators are pure read-only — no DB
writes.

### E.3 — Composer

```python
def compose_briefing(tenant_id: int, kind: str,
                     today: date, db: Session) -> str:
    # 1. Run every evaluator concurrently (or serially — there are
    #    only ~12, single-digit ms each).
    candidates = [d(tenant_id, today, db) for d in ALL_DETECTORS]
    candidates = [c for c in candidates if c is not None]

    # 2. Apply cooldown filter (read briefing.signal_fired events).
    candidates = filter_by_cooldown(candidates, tenant_id, today, db)

    # 3. Sort by tier ASC, confidence DESC, severity DESC.
    candidates.sort(...)

    # 4. Diversity rule — drop same-category duplicates after slot 1.
    selected = apply_diversity(candidates, max_signals=3)

    # 5. If selected is empty, fall back to v6.3.4 templated content.
    if not selected:
        return build_morning_briefing(tenant_id, ..., db)

    # 6. Render header + each selected signal's localised message.
    # 7. Persist briefing.signal_fired events for cooldown tracking.
    return render(selected)
```

### E.4 — Integration point

In `dispatcher._build_content_for_kind()`:

```python
def _build_content_for_kind(tenant, kind, today_in_tz, db):
    if feature_flag(tenant, 'pattern_briefing'):  # new flag
        return compose_briefing(tenant.id, kind, today_in_tz, db)
    if kind == 'morning':
        return build_morning_briefing(...)  # existing path
    ...
```

Behind a feature flag so the rollout is reversible per-tenant.

### E.5 — Tests

- **Unit per evaluator** with seeded fixtures (one tenant, one
  positive case, one negative case, suppression edges).
- **Composer integration tests:**
  - No signals fire → fallback to templated output.
  - 5 signals fire, only 3 surface, diversity rule respected.
  - Escalation: same signal day 1 vs day 2 produces different messages.
  - Cooldown: same signal day 2 (no escalation) is skipped.
- **No E2E.** The dispatcher is already tested at the cron level; the
  composer is a pure function from (tenant, date, db) → string.

### E.6 — Migration / data-prerequisite work

If Q1 (events-based attendance log) is approved, **one tiny code change
outside v6.3.11's evaluator package** is required:

In `backend/app/services/whatsapp_checkin.py:save_checkin_state()`,
after the Redis SETEX, also stage:

```python
db.add(Event(
    tenant_id=tenant_id,
    event_type='attendance.recorded',
    entity_type='checkin',
    entity_id=None,
    actor_user_id=manager_user_id,
    source='whatsapp',
    payload={
        'for_date': for_date.isoformat(),
        'absent_employee_ids': absent_ids,
        'down_machine_ids': down_machine_ids,
    },
))
db.commit()
```

This is ~10 lines, no migration, no schema change. After 7 days of data
accumulates, attendance signals can fire.

---

## Section F — What's NOT in v6.3.11

Explicit out-of-scope list:

- **Entity extraction from WhatsApp messages** — the v6.3.13–15 stream.
  Signals read existing tables only.
- **Day-7 wow gate composition layer** — v6.3.16. v6.3.11 produces a
  *daily* `day_7` signal; the wow-gate selection logic that decides
  *what* to surface on day 7 across cumulative signals is its own ticket.
- **Day-30 savings receipt** — depends on v6.24 KPI Baseline (planned,
  not shipped).
- **Settings UI** — no per-tenant customisation surface for signal
  thresholds or cooldowns. v6.3.11 ships with hardcoded defaults that
  the user signs off on in Section G. Settings UI = v6.3.20.
- **Real-time / event-driven alerts** — signals are still aggregated
  into the morning + evening briefings. No push-on-event. No SMS.
- **Multi-language template variants** beyond hi-en, hi, en — already
  in templates.py, no expansion in v6.3.11.
- **Conflict-detection signal** (`conflict_jobs_count`) — UNTIL the
  source of "8 conflicts detected" is identified (Q4). Spec'd, not
  shipped.
- **Status normalisation migration** (Section C option a) — deferred
  to v6.4.x or whenever user prioritises.

---

## Section G — Open questions for user review

Answer inline in this file, then ping for Session 2.

### Q1. Persist manager check-in to events table going forward?

**Why this is the most important question.** Today the check-in state
expires after 24 hours in Redis. Without history, **none of the
attendance signals (B.1) can fire reliably** — they would have to fall
back to the near-empty `employee_leaves` table.

Recommendation: yes, add the 10-line `db.add(Event(...))` to
`save_checkin_state()` as a v6.3.11 prerequisite (no migration needed —
events table accepts arbitrary event_type strings).

**Your answer:**

---

### Q2. Consecutive absence threshold

What count triggers `consecutive_absence`?
- **2 working days** (recommended; matches MSME owner anxiety threshold)
- **3 working days** (more conservative, fewer false alarms)
- **Industry-specific** (printing: 2, fabrication: 3, etc.)

**Your answer:**

---

### Q3. Low-utilisation threshold

What "% busy in last 7 days" counts as low?
- **30%** (recommended starter; expect tuning after pilot data)
- **50%** (more aggressive)
- **Industry-specific**

**Your answer:**

---

### Q4. `conflict_jobs_count` — where does the count come from?

The "8 conflicts detected" string the user previously pasted suggests
there's a conflicts table or a `has_conflict` column somewhere. I did
not find one on the Job model in Section A.3. Possibilities:
- Computed at scheduler-run time and stored in a Redis key
- A column I missed (please paste the file/line if you know)
- A derived count from `original_start_date IS NOT NULL` (scheduler
  moved the job → potential conflict marker)

If the source isn't easy to identify, drop this signal from v6.3.11 and
add it back when conflict detection becomes a first-class column.

**Your answer:**

---

### Q5. Revenue-at-risk currency threshold

Below what amount is `revenue_at_risk` not worth surfacing?
- **₹50,000** (recommended for small shops)
- **₹1,00,000**
- **% of last-month revenue** (depends on KPI baseline — out of scope)

**Your answer:**

---

### Q6. Status normalisation strategy

(See Section C.) Pick one:
- **(a) Migration 029 in v6.3.11** — clean future, scope creep risk
- **(b) Application-level lowercase** — recommended; ship v6.3.11
  cleanly, queue migration for v6.4.x

**Your answer:**

---

### Q7. New-tenant quiet period

Do not fire signals for tenants younger than:
- **7 days** (recommended — let the listening week happen first)
- **14 days**
- **0 days** (signals fire immediately if data supports them)

**Your answer:**

---

### Q8. Contractor inclusion

Contractors are excluded from attendance signals by default. Override?
- **Always exclude** (recommended; variable presence is the deal)
- **Include with a different (looser) threshold**
- **Owner-configurable** (deferred to v6.3.20 settings UI)

**Your answer:**

---

### Q9. Signal escalation message language

For escalations (e.g. day 2 → day 3 of absence), the message changes
shape. Should the bot use:
- **Numeric counter** ("3 din se gayab") — recommended; concrete and
  unambiguous
- **Adverbs** ("ab kafi din se nahi aaye") — softer, less precise
- **Both, escalating** (numeric for ≤ 5 days, then "kafi din")

**Your answer:**

---

### Q10. Idle-day fallback wording

When no signal qualifies, the briefing falls back to v6.3.4 templated
content. Append a trailing line?
- **Yes** ("Aaj koi alag pattern nahi dikha — sab routine hai.")
- **No** (silence-by-omission is meaningful enough)
- **Only after Day 7** (don't whisper "no patterns" on day 2 when the
  bot hasn't earned the right to claim "I was watching")

**Your answer:**

---

## Closing notes

After you answer Q1–Q10, Session 2 will:

1. Add the `attendance.recorded` event write to `save_checkin_state()`
   if Q1 is approved.
2. Build the `briefing_intelligence` package per Section E.1.
3. Add the feature flag `pattern_briefing` (default OFF per tenant).
4. Wire `compose_briefing` into `dispatcher._build_content_for_kind()`
   behind the flag.
5. Per-signal unit tests + composer integration tests.
6. Tag v6.3.11 once the four standard verification gates pass.

No code, no commits, no SRS / ledger / changelog edits in this design
session. Ready for your review.
