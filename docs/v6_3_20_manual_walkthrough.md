# v6.3.20 manual WhatsApp walkthrough

Acceptance harness for the v6.3.20 NL push-settings updater. Covers the
seven scenarios from the v6.3.20 prompt (`v6_3_20.md` lines 717–735),
plus the web-UI tool-isolation check (step 8) and the pytest regression
gate (step 9). Run end-to-end before tagging v6.3.20.

> **PREREQUISITE — v6.3.20 part 2 plumbing must be merged first.**
> The current `main` ships only the service module + tool definitions
> (commit `6aea025`). Until `actor_user_id` + `phone_number` are
> plumbed through `app/routers/whatsapp.py:1075` →
> `whatsapp_bridge.process_message` → `ai_service.run_ai_chat` →
> `execute_tool`, the v6.3.20 write tools will refuse with
> `tool_requires_whatsapp_channel` and step 1 below will fail.
> If `git log --oneline | grep "v6.3.20 part 2"` returns nothing,
> stop and ship part 2 first.

## Setup

- Backend running locally: `cd backend && uvicorn app.main:app --reload`
- `.env` defaults: `WHATSAPP_MOCK_MODE=True` (Settings simulator mode).
- Test tenant: `what@what.what` / `qazx1234` / `tenant_id=12` / phone
  `+919876543210` (top-tier owner — see CLAUDE.md §22).
- A second phone for step 5 (manager). If the test tenant doesn't have
  one wired up, seed it via `/api/v1/whatsapp/link-phone` with
  `phone_role='manager'`. Note its E.164 number — you'll send messages
  from it.
- Postgres or the dev DB so the `events` audit table can be inspected.
  Suggested shell aliases:

```bash
export OWNER_PHONE='+919876543210'
export MANAGER_PHONE='+91XXXXXXXXXX'   # whatever you seeded
export PSQL='psql -h localhost -U postgres -d zetaops'
```

- A JWT for the test tenant — needed for the `/whatsapp/debug/dispatch`
  call in step 2 and the `/api/v1/ai_chat` call in step 8:

```bash
export TOKEN=$(curl -sX POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"what@what.what","password":"qazx1234"}' | jq -r .access_token)
echo "$TOKEN" | head -c 20   # sanity-check the token starts with eyJ
```

All `simulate` requests use the same shape:

```bash
curl -sX POST http://localhost:8000/api/v1/whatsapp/simulate \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"$OWNER_PHONE\",\"message\":\"<text>\",\"type\":\"text\"}" \
  | jq
```

---

## Reset between scenarios

The scenarios assume tenant 12 starts each independent block in a known
state. Snapshot before scenario 1, reset between any two scenarios that
write to the same column, and snapshot again at the end.

**Starting-state snapshot** (run before scenario 1 and capture the output):

```sql
SELECT id, briefing_morning_enabled, briefing_morning_time,
       briefing_evening_enabled, briefing_evening_time,
       briefing_timezone, briefing_working_days,
       morning_sections, evening_sections, push_paused_until
FROM tenants WHERE id = 12;
```

If `briefing_morning_enabled` is `false`, `briefing_morning_time` is not
`07:30`, or `push_paused_until` is set, run the reset block below before
proceeding so the assertions match.

**Reset block** (re-run between any scenarios that modify the same
columns — explicitly called out in each scenario where order matters):

```sql
-- reset all v6.3.20 audit rows for tenant 12
DELETE FROM events
WHERE tenant_id = 12
  AND event_type = 'tenant.push_setting_changed';

-- reset the columns we touch in this walkthrough
UPDATE tenants
SET briefing_morning_enabled = TRUE,
    briefing_morning_time    = TIME '07:30',
    briefing_evening_enabled = TRUE,
    briefing_evening_time    = TIME '18:30',
    briefing_timezone        = 'Asia/Kolkata',
    briefing_working_days    = '1,2,3,4,5,6',
    push_paused_until        = NULL
WHERE id = 12;
```

Pending Redis state can stick around between scenarios when a previous
HAAN/NAHI didn't fire (timeout, parse miss). Clear it explicitly:

```bash
# Real Redis:
redis-cli del "whatsapp:pending_action:$OWNER_PHONE"
redis-cli del "whatsapp:pending_action:$MANAGER_PHONE"

# Mock mode (no UPSTASH_REDIS_URL): restart uvicorn, the in-memory dict resets.
```

---

## When a step fails

Don't proceed to the next scenario on a failure — the dirty state
poisons later assertions. Instead, capture and retry:

1. **Capture immediately** before doing anything else:
   - Full backend log tail (`uvicorn` stdout) for the request, including
     the AI tool-call dump if visible.
   - The full response body from the failing `simulate` call.
   - The `events` table snapshot for `tenant_id=12` ordered by `id` desc.
   - Pending action key in Redis (or `_mock_sessions` dump).
2. **Reset state** using the reset block above before retrying.
3. **Common failure modes and what they mean:**
   - Reply text starts with `Maafi kijiye, abhi AI service available
     nahi hai` → Groq API failure, not a v6.3.20 bug. Retry the request.
   - Reply text contains `tool_requires_whatsapp_channel` → part 2
     plumbing not merged. Stop, ship part 2 first.
   - Reply text contains `<function=...>` or `<|python_tag|>` markup →
     v6.3.9 retry path didn't fire. Inspect `ai_service.run_ai_chat`
     log line `Groq rejected tool call (tool_use_failed)`.
   - Confirmation prompt missing for a write intent → LLM bypassed the
     staging path. Inspect `execute_tool`'s `update_push_setting` /
     `pause_push` branch — should have returned
     `status: "confirmation_required"`.
   - Confirmation prompt fired but HAAN reply did not commit → router
     YES handler at `whatsapp.py:831` didn't pick up the pending
     action. Check the Redis key spelling matches
     `whatsapp:pending_action:<phone>`.
   - DB column changed but no audit row → the service module's audit
     write failed. Check Postgres logs for the `INSERT INTO events`
     statement; the entire transaction should have rolled back.
4. **File the failure** in the v6.3.20 part 2 PR (or a follow-up issue)
   with the captures above. Do NOT tag v6.3.20 with any failed
   scenario open.

---

## 1. Time change — happy path with HAAN confirm

Run the reset block first. Send (as owner):

```
morning briefing 8 baje karo
```

**Expected response.** Hinglish confirmation from `build_confirmation_prompt`
along the lines of:

> Kya main ye karna chahta hoon:
> Set morning briefing time to 08:00.
>
> Confirm karne ke liye: HAAN
> Cancel karne ke liye: NAHI
> (5 minute mein reply nahi kiya toh automatically cancel ho jayega)

The `Set ... to ...` line comes verbatim from the `snippet_en` field in
`execute_tool`'s `update_push_setting` branch. The "Kya main ye…" /
"Confirm karne ke liye" scaffolding comes from
`whatsapp_actions.build_confirmation_prompt`.

**Expected DB state after the prompt (BEFORE you reply HAAN):**

```sql
SELECT briefing_morning_time FROM tenants WHERE id = 12;
-- still 07:30 — column is NOT touched until confirmation

SELECT count(*) FROM events
WHERE tenant_id = 12
  AND event_type = 'tenant.push_setting_changed';
-- 0 — audit row only written on commit
```

The pending action lives in Redis (or `_mock_sessions` if no
`UPSTASH_REDIS_URL`):

```bash
# Redis case:
redis-cli get "whatsapp:pending_action:$OWNER_PHONE"
# Mock case: restart uvicorn would clear it; otherwise just reply HAAN
# below and trust the reply path.
```

Now reply `HAAN`:

```bash
curl -sX POST http://localhost:8000/api/v1/whatsapp/simulate \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"$OWNER_PHONE\",\"message\":\"HAAN\",\"type\":\"text\"}"
```

**Expected response.** Success snippet from
`PushSettingChangeResult.snippet["hi_en"]`, which the service builds as
`f"{spec.label_en.capitalize()} {new_value} kar diya."` — concretely:

> Morning briefing time 08:00 kar diya.

The English fallback (`snippet["en"]`) reads `Updated morning briefing
time to 08:00.` and would surface only if the service module's `hi_en`
key were missing.

**Expected DB state after HAAN:**

```sql
SELECT briefing_morning_time FROM tenants WHERE id = 12;
-- 08:00:00

SELECT event_type, source, actor_user_id, payload
FROM events
WHERE tenant_id = 12
  AND event_type = 'tenant.push_setting_changed'
ORDER BY id DESC LIMIT 1;
-- payload: {"field":"briefing_morning_time", "old_value":"07:30",
--          "new_value":"08:00", "source_phrase":"morning briefing 8 baje karo"}
-- source: 'whatsapp', actor_user_id: <owner user.id>
```

---

## 2. Pause — restated date range MUST appear

Run the reset block first. Send (as owner) on a Monday — pick today and
read the dates carefully:

```
agle 5 din chuti hai, briefing band karo
```

**Expected confirmation prompt.** Must contain a `pause_range_human`
string of the form `Mon Mmm DD through Fri Mmm DD, resume Sat Mmm DD`
covering 5 calendar days starting today in Asia/Kolkata. If the date
range is missing or wrong, FAIL — that's the load-bearing check the
prompt requires. Confirm the math by hand: `today + (5 - 1)` days.

Reply `HAAN`. **Expected DB state:**

```sql
SELECT push_paused_until FROM tenants WHERE id = 12;
-- today + 4 days, in Asia/Kolkata local

SELECT payload->>'days', payload->>'today_local', payload->>'new_value',
       payload->>'timezone'
FROM events
WHERE tenant_id = 12
  AND event_type = 'tenant.push_setting_changed'
  AND payload->>'field' = 'push_paused_until'
ORDER BY id DESC LIMIT 1;
-- days: '5', today_local: '<today ISO>', timezone: 'Asia/Kolkata',
-- new_value: <today + 4 ISO>
```

**Dispatcher pause verification.** Trigger morning dispatch via the
debug endpoint; it must skip with `paused`:

```bash
curl -sX POST http://localhost:8000/api/v1/whatsapp/debug/dispatch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"morning","tenant_id":12,"now":"<today T07:30:00 IST>","force_send":false}'
```

Response should carry `skip_reason: "paused"` and write one
`push.morning_skipped_paused` event with `paused_until` matching the
column. (The pause check itself was shipped in v6.3.19 — this step is
just confirming v6.3.20 wired into it correctly.)

---

## 3. Read-only — no confirmation, no audit row

Capture the audit count first:

```sql
SELECT count(*) FROM events WHERE tenant_id = 12
  AND event_type = 'tenant.push_setting_changed';
```

Send (as owner):

```
morning briefing kab hai?
```

**Expected response.** A free-form narration that mentions, at minimum,
the morning briefing time, the evening recap time, the working days,
and the current pause state (if any). Exact wording will vary — the
LLM phrases this freely from `get_push_settings`'s structured return.
Look for *intent and content*, not literal text. Anything along the
lines of "morning briefing X baje, evening recap Y baje, Mon–Sat,
paused until Z" passes.

**No confirmation prompt should appear** — `get_push_settings` is
read-only and `execute_tool` returns the data directly without staging.

**Expected DB state.** Audit count unchanged from the snapshot above.
This is the hard assertion for `get_push_settings` — read-only must
NEVER write.

---

## 4. Sections — desktop redirect, no tool call

Send (as owner):

```
morning me attendance section hatao
```

**Expected response.** Polite redirect *intent* in the user's language
that mentions the desktop UI as the place to edit sections. Exact
wording varies — the system prompt provides the example
`"Briefing ke sections sirf desktop se badal sakte ho. Apne computer
pe Settings → Push Briefings kholo."` but the LLM will paraphrase.
Look for: (a) refusal to apply the change, and (b) a pointer to the
desktop app / Settings → Push Briefings.

**No confirmation prompt.** **No tool call to `update_push_setting`.**
**No DB write.** Audit count unchanged.

If you see a confirmation prompt or any DB write, FAIL — the LLM tried
to call `update_push_setting` with `morning_sections`, which means
either the system prompt addendum or the tool enum (which excludes
those fields) didn't bind correctly.

---

## 5. Non-top-tier — polite refusal

Send (as the `MANAGER_PHONE` you set up in Setup):

```
morning briefing 8 baje karo
```

**Expected response.** Polite refusal in the user's language. Look for
intent only: declines the change, and either names the top-tier roles
(Owner / Co-Owner / Factory Manager) or suggests asking the Owner.
**No confirmation prompt.** **No DB write.**

`PushSettingForbidden` with code `forbidden_not_top_tier` is the
underlying error; the user-facing message is in `_MSG` in
`push_settings_service.py`.

---

## 6. Bad time format — validator rejects, AI re-asks

Run the reset block first so an accidental success would be visible.

Send (as owner):

```
morning briefing 25 baje karo
```

**Expected response.** Validator rejection at stage time —
`invalid_time_format`. The AI should surface a re-ask in the user's
language. Intent to look for: refuses the change, asks for a 24-hour
HH:MM time, gives an example like `08:00` or `20:00`. Exact wording
varies (the canonical message in `_MSG["invalid_time_format"]["hi_en"]`
is `"Time HH:MM 24-hour format me dijiye, jaise 08:00 ya 20:00."`).

**Expected DB state.** Column still 07:30, no audit row, no pending
action in Redis (the validator failure happens before staging).

**Variant — `morning briefing 8pm karo`.** Two possible outcomes; both
acceptable but the *expected* path is normalisation:

- *Pass path (canonical):* the LLM follows the system prompt rule
  `"Convert '8 pm' to '20:00'."` and calls `update_push_setting` with
  `value="20:00"`. You see a confirmation prompt for `Set evening recap
  time to 20:00.` (or morning, depending on which field the LLM picked).
  This is the success outcome; reply HAAN to commit, then run the
  reset block.
- *Acceptable fallback:* the LLM passes `"8pm"` raw to the tool and the
  validator rejects with `invalid_time_format`, same as `25 baje`. This
  is a soft failure — the LLM should have normalised but the prompt
  rule wasn't bindng tight enough. File this as a system-prompt
  follow-up, not a v6.3.20 blocker.

---

## 7. Pause range — AM/PM ambiguity test

Send (as owner) on a Tuesday:

```
kal se 3 din ke liye band karo
```

**Expected confirmation prompt.** Two acceptable outcomes:

- *Canonical:* the LLM passes `days=3` with the understanding that
  "starting tomorrow, 3 days" = today + 2 (Wed counts as day 1). The
  confirmation prompt restates the range as
  `Wed Mmm DD through Fri Mmm DD, resume Sat Mmm DD`.
- *Equally acceptable:* the LLM detects the ambiguity (does "starting
  tomorrow" shift the day-1 anchor?) and asks the user to clarify
  before calling the tool. Per the system prompt rule "do not guess",
  this is the safer path.

What FAILS: the LLM calls `pause_push` with `days=3` AND the
confirmation prompt restates the range starting *today* not *tomorrow*
— that's an off-by-one the user can't catch and we ship.

Reply `NAHI` to verify the cancel path:

```bash
curl -sX POST http://localhost:8000/api/v1/whatsapp/simulate \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"$OWNER_PHONE\",\"message\":\"NAHI\",\"type\":\"text\"}"
```

**Expected:** message says cancelled, pending action cleared, no DB
write.

```bash
# Real Redis:
redis-cli get "whatsapp:pending_action:$OWNER_PHONE"
# (nil)

# Mock mode (no UPSTASH_REDIS_URL):
# redis-cli is not connected to anything; instead, send any non-confirm
# text and verify the response is a normal AI reply (not a re-prompt of
# the pending pause). If you see "Confirm karne ke liye: HAAN" again,
# the pending action is still staged — clear it by restarting uvicorn.
```

---

## 8. Web-UI tool isolation — the v6.3.20 tools must NOT fire from desktop

This is the security-boundary check that justifies the optional-kwargs
design from part 1. The three v6.3.20 tools (`update_push_setting`,
`pause_push`, `get_push_settings`) require `actor_user_id` AND
`phone_number`. The desktop AI chat (`/api/v1/ai_chat`) does not pass
either — so the write tools must refuse with
`tool_requires_whatsapp_channel`.

Send via the web-UI AI chat using $TOKEN from Setup:

```bash
curl -sX POST http://localhost:8000/api/v1/ai_chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"set morning briefing to 8 AM"}]}' \
  | jq
```

**Expected response.** Either:

- The LLM declines politely without calling any tool (system prompt
  routing said "this is a WhatsApp tool"), OR
- The LLM calls `update_push_setting`, the tool returns
  `{"error": "tool_requires_whatsapp_channel", ...}`, and the LLM
  surfaces a "please use the desktop Settings UI" reply.

What FAILS: a confirmation prompt appears and a HAAN reply via the
web UI commits the change. That means part 2 plumbing leaked
`actor_user_id` into the web-UI call site — the web UI must NEVER be
able to drive these tools.

Verify no DB write:

```sql
SELECT briefing_morning_time FROM tenants WHERE id = 12;
-- unchanged from before this step

SELECT count(*) FROM events
WHERE tenant_id = 12 AND event_type = 'tenant.push_setting_changed'
  AND created_at > now() - interval '1 minute';
-- 0
```

---

## 9. Regression — pytest still green

```bash
cd backend
./venv/Scripts/python.exe -m pytest tests/services/test_push_settings_service.py -v
./venv/Scripts/python.exe -m pytest tests/ -m "not integration" -q --tb=no
```

**Expected:** 26 passing in the dedicated suite; **1078 passing**
unit-tier overall (matches the v6.3.20 part 1 baseline). If part 2
added new tests, that count goes up — record the new baseline in
`DELIVERY_LEDGER.md`.

---

## Sign-off checklist

- [ ] Step 1 — time change confirmed end-to-end (column updated, audit row written)
- [ ] Step 2 — pause confirmed; `pause_range_human` appears in confirmation; dispatcher skips with `paused`
- [ ] Step 3 — read-only narration with zero audit rows written
- [ ] Step 4 — desktop redirect, no DB write, no confirmation prompt
- [ ] Step 5 — non-top-tier refusal, no DB write
- [ ] Step 6 — `25:00` rejected, AI re-asks for HH:MM
- [ ] Step 7 — pause range restated (or LLM asks for clarification), NAHI cancels cleanly
- [ ] Step 8 — web-UI AI chat does NOT commit a push-setting change
- [ ] Step 9 — pytest green at the recorded baseline

When all nine are checked, tag `v6.3.20` (annotated, matching the
v6.3.x series convention):

```bash
git tag -a v6.3.20 -m "v6.3.20 — WhatsApp NL push-settings updater"
git push origin v5-whatsapp                # push the branch first
git push origin v6.3.20                    # then push the tag
```

Then update `DELIVERY_LEDGER.md` `Last updated:` and flip the
`[Unreleased]` v6.3.20 entry in `CHANGELOG.md` to a tagged
`## [v6.3.20] — YYYY-MM-DD` section per the doc-trinity rule.
