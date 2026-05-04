# app/services/briefing_intelligence/signals.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Signal contract for v6.3.11 pattern-aware briefings — the single
# dataclass returned by every evaluator. Per spec Section E.2.
#
# WHO CALLS THIS FILE
# - app/services/briefing_intelligence/composer.py — sorts, filters,
#   and renders SignalResult instances.
# - app/services/briefing_intelligence/cooldown.py — reads severity
#   from a SignalResult to compare against the prior fired event.
# - app/services/briefing_intelligence/catalog/job.py and other
#   evaluators — return SignalResult or None.
#
# WHAT THIS FILE CALLS
# - dataclasses.dataclass / field
# - typing.Optional
#
# DESIGN NOTES
# - `None` from an evaluator means "did not fire". `suppression_reasons`
#   is a debug aid the composer can log when a candidate is dropped by
#   cooldown / diversity / quiet-period rules.
# - severity_score is a free float, not bounded. The composer uses
#   strict-greater-than for escalation, so 3.0 vs 3.0 == cooldown holds;
#   3.0 vs 4.0 == escalation fires.
# - subject_entity_id is Optional. Tenant-wide signals (e.g.
#   delayed_jobs_count) carry None; per-entity signals (e.g.
#   consecutive_absence on employee_id=84) carry the id. Cooldown lookup
#   matches both NULL and the integer.

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignalResult:
    """One fired signal candidate. See spec Section E.2 for the contract.

    Fields:
        signal_id:           Stable string identifier ('delayed_jobs_count').
                             Used by cooldown lookup and as the payload key
                             on briefing.signal_fired events.
        category:            One of 'attendance' | 'machine' | 'job' |
                             'customer' | 'tenancy' | 'health'. Used by
                             the diversity rule (D.3).
        tier:                1 (always wins), 2 (high-confidence), 3
                             (experimental). Sort key — lower wins.
        confidence:          'high' | 'medium' | 'low'. Tie-break inside
                             a tier — higher wins.
        subject_entity_type: 'employee' | 'machine' | 'job' | 'customer'
                             | 'tenant' — what the message is about.
        subject_entity_id:   FK into the relevant table; None for
                             tenant-wide signals.
        severity_score:      Used by the escalation rule (D.5). The
                             composer fires the candidate even inside
                             cooldown when this is strictly greater than
                             the prior fired score.
        message_hi_en:       Hinglish line that goes into the briefing.
        message_en:          English fallback (currently unused at the
                             render layer; kept for future locale work).
        cooldown_days:       Days to suppress repeats absent escalation.
        suppression_reasons: Debug breadcrumb populated by the composer
                             when a candidate is dropped. Empty for
                             surfaced signals.
    """

    signal_id: str
    category: str
    tier: int
    confidence: str
    subject_entity_type: str
    subject_entity_id: Optional[int]
    severity_score: float
    message_hi_en: str
    message_en: str
    cooldown_days: int
    suppression_reasons: list[str] = field(default_factory=list)
