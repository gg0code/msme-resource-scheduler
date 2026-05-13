import sys
sys.path.insert(0, ".")

from app.services import message_formatters as f
from app.services.whatsapp_meta_templates import META_TEMPLATES, bound_templates

print("=" * 60, "\nMORNING_BRIEFING_EN\n", "=" * 60)
print(f.MORNING_BRIEFING_EN.format(
    "Tuesday, 30 April",         # {0} — date
    "3",                         # {1} — jobs_starting
    "1 (Patel brochures)",       # {2} — continuing
    "10 of 11",                  # {3} — crew_expected
    "Rakesh on leave",           # {4} — flag
    "Confirm Bhatia paper",      # {5} — next_step
))

print("\n", "=" * 60, "\nMORNING_BRIEFING_HI\n", "=" * 60)
print(f.MORNING_BRIEFING_HI.format(
    "मंगलवार, 30 अप्रैल",        # {0} — date
    "3",                         # {1} — jobs_starting
    "1 (पटेल brochures)",        # {2} — continuing
    "10 में से 11",              # {3} — crew_expected
    "राकेश छुट्टी पर",            # {4} — flag
    "9 बजे से पहले paper confirm",  # {5} — next_step
))

print("\n", "=" * 60, "\nCONFLICT_ALERT_EN\n", "=" * 60)
print(f.CONFLICT_ALERT_EN.format(
    "Bhatia wedding cards",      # {0} — job_a
    "Reliance flyers",           # {1} — job_b
    "Machine 2",                 # {2} — resource
    "Tomorrow 10 AM — 1 PM",     # {3} — window
    "Move Reliance to Machine 3",  # {4} — next_step
))

print("\n", "=" * 60, "\nDELAY_ALERT_EN\n", "=" * 60)
print(f.DELAY_ALERT_EN.format(
    "Wedding Card Run",          # {0} — job_name
    "Royal Events",              # {1} — customer
    "about 45 minutes",          # {2} — time_remaining
    "820 of 850 cards printed",  # {3} — progress
    "Modi pamphlets",            # {4} — next_job
))

print("\n", "=" * 60, "\nAI_REPLY_HEADER\n", "=" * 60)
print(f.AI_REPLY_HEADER.format(first_name="Sharma ji"))

print("\nMeta registry summary:")
print("  total entries:", len(META_TEMPLATES))
print("  bound to Python:", len(bound_templates()))
for k, v in bound_templates().items():
    print(f"    {k} -> {v['python_constant']}")
