# app/services/day7_thresholds.py
# Branch: v5-whatsapp
# Iteration: v6.3.16 (Day-7 First-Insight Gate)
#
# FILE PURPOSE
# Pure-data module. Holds the numeric thresholds the Day-7 First-Insight
# Gate uses to decide which of the four candidate signals (attendance,
# skill bottleneck, machine utilisation, recurring customer) crosses
# its bar. No logic, no DB access, no imports beyond the standard
# library — anything heavier belongs in app/services/day7_insight.py.
#
# WHO CALLS THIS FILE
# - app/services/day7_insight.py — every signal detector reads its
#   threshold(s) from here. Keeping the constants in a separate file
#   means the v6.4.0 engagement-ladder package can move this file
#   wholesale into engagement_ladder/thresholds.py without touching
#   the detectors.
# - tests/services/test_day7_insight.py — fixtures import the
#   constants so the tests assert on the same numbers production uses
#   rather than embedding magic literals.
#
# WHAT THIS FILE CALLS
# - Nothing. Stdlib only. Adding a non-stdlib import here is a sign
#   the module is taking on logic that belongs in day7_insight.py.
#
# DESIGN NOTES
# - Every value is currently an educated guess. The dispatcher pilot
#   will produce real distributions; tune from there. Each constant's
#   comment records the v6.3.16-launch value so future tuners can see
#   the starting point.
# - Constants are grouped by signal so a tuner reading a single
#   detector function in day7_insight.py can find every knob that
#   controls it in one block here.
# - Look-back window is 7 days everywhere because the gate is the
#   "first 7 days" gate. v6.4.0's full ladder will introduce per-stage
#   windows; until then a single LOOKBACK_DAYS = 7 covers the lot.
# - SUPPRESS_IF_DAY_COUNT_OVER comes from the Q1 confirmation: a
#   tenant whose first_briefing_sent_at is far enough in the past
#   that day_count > 14 on the gate's first evaluation is silently
#   marked "fired" without sending. Prevents post-hoc Day-7 messages
#   to existing pilot tenants.
#
# FORWARD-COMPAT
# - When this file moves to engagement_ladder/thresholds.py in v6.4.0,
#   the receiving package should re-export the same names so existing
#   imports keep working during the transition. v6.3.16 callers must
#   import from this exact path; the move is a v6.4.0 problem.

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# How far back every Day-7 signal looks. The gate is, by definition,
# the "first 7 days" insight, so 7 calendar days is the right window.
# v6.4.0 may make this per-signal; for v6.3.16 one number covers all.
LOOKBACK_DAYS: int = 7

# Day-count value at which the gate stops trying to fire. Tenants whose
# computed day_count exceeds this on first evaluation are marked
# "fired" without sending — keeps existing pilot tenants from receiving
# a confusing post-hoc Day-7 message. 14 is twice the look-back so a
# tenant who was offline for one week and came back still gets a fire,
# but a tenant whose first briefing was a month ago does not.
SUPPRESS_IF_DAY_COUNT_OVER: int = 14


# ---------------------------------------------------------------------------
# Signal 1: attendance pattern
# ---------------------------------------------------------------------------
# The gate fires on attendance when EITHER condition crosses threshold:
#   (a) a single worker is marked absent on at least
#       ATTENDANCE_MIN_ABSENT_DAYS_PER_WORKER of the last
#       LOOKBACK_DAYS working days, OR
#   (b) the same weekday (e.g. every Monday) shows at least
#       ATTENDANCE_MIN_WORKERS_SAME_WEEKDAY distinct workers absent
#       across the look-back.
#
# (a) catches "Suresh keeps disappearing"; (b) catches "Mondays are
# rough". Both are real first-week patterns reported during the pilot
# scoping.
ATTENDANCE_MIN_ABSENT_DAYS_PER_WORKER: int = 4
ATTENDANCE_MIN_WORKERS_SAME_WEEKDAY: int = 2


# ---------------------------------------------------------------------------
# Signal 2: skill bottleneck
# ---------------------------------------------------------------------------
# A skill is "bottlenecked" when one worker handles SKILL_BOTTLENECK_RATIO
# (70%) or more of the jobs requiring that skill in the look-back.
# Below SKILL_BOTTLENECK_MIN_JOBS the ratio is too noisy to act on —
# 1-of-1 = 100% but tells the owner nothing. 3 jobs is the smallest
# count where 70% is meaningful (one of three workers ≈ 33%, two ≈ 67%,
# all three ≈ 100%, so 70% means "two or three out of three").
SKILL_BOTTLENECK_RATIO: float = 0.70
SKILL_BOTTLENECK_MIN_JOBS: int = 3


# ---------------------------------------------------------------------------
# Signal 3: machine utilisation
# ---------------------------------------------------------------------------
# Machine utilisation is dispersion. The gate fires when (max_hours /
# min_hours) across machines >= MACHINE_UTILISATION_RATIO_THRESHOLD,
# where min_hours is taken from machines that ran at least
# MACHINE_UTILISATION_MIN_HOURS_PER_DAY hours/day on average over the
# look-back. The min-hours floor stops "machine that ran for 6 minutes
# total" from dragging the ratio to infinity and triggering on noise.
MACHINE_UTILISATION_RATIO_THRESHOLD: float = 4.0
MACHINE_UTILISATION_MIN_HOURS_PER_DAY: float = 0.5

# Minimum number of distinct machines required for the signal to fire.
# Two machines is the smallest case where "one is 4x the other" is a
# meaningful observation. With one machine the spread is undefined.
MACHINE_UTILISATION_MIN_MACHINES: int = 2


# ---------------------------------------------------------------------------
# Signal 4: recurring customer name
# ---------------------------------------------------------------------------
# The gate fires when a customer name pulled from extraction_candidates
# (entity_type='customer') has mention_count >=
# CUSTOMER_RECURRING_MIN_MENTIONS in the last LOOKBACK_DAYS days AND
# does not yet appear in jobs.customer for this tenant. The substring-
# overlap rule excludes aliases of existing customers (e.g. "Patel
# Trading Co." is the same business as "Patel Traders") when both
# strings share a continuous case-insensitive substring of at least
# CUSTOMER_RECURRING_ALIAS_MIN_OVERLAP characters in either direction.
# 5 mentions in 7 days is a credible "they keep coming up" threshold;
# 4 characters of overlap rejects coincidental short shared tokens
# like "Co." or "Pvt." while catching real surname matches.
CUSTOMER_RECURRING_MIN_MENTIONS: int = 5
CUSTOMER_RECURRING_ALIAS_MIN_OVERLAP: int = 4
