import sys
sys.path.insert(0, ".")

from app.services import message_formatters as f
from app.services.whatsapp_meta_templates import META_TEMPLATES, bound_templates

print("=" * 60, "\nMORNING_BRIEFING_EN\n", "=" * 60)
print(f.MORNING_BRIEFING_EN.format(
    date="Tuesday, 30 April",
    jobs_starting="3",
    continuing="1 (Patel brochures)",
    crew_expected="10 of 11",
    flag="Rakesh on leave",
    next_step="Confirm Bhatia paper",
))

print("\n", "=" * 60, "\nMORNING_BRIEFING_HI\n", "=" * 60)
print(f.MORNING_BRIEFING_HI.format(
    date="मंगलवार, 30 अप्रैल",
    jobs_starting="3",
    continuing="1 (पटेल brochures)",
    crew_expected="10 में से 11",
    flag="राकेश छुट्टी पर",
    next_step="9 बजे से पहले paper confirm",
))

print("\n", "=" * 60, "\nCONFLICT_ALERT_EN\n", "=" * 60)
print(f.CONFLICT_ALERT_EN.format(
    job_a="Bhatia wedding cards",
    job_b="Reliance flyers",
    resource="Machine 2",
    window="Tomorrow 10 AM — 1 PM",
    next_step="Move Reliance to Machine 3",
))

print("\n", "=" * 60, "\nDELAY_ALERT_EN\n", "=" * 60)
print(f.DELAY_ALERT_EN.format(
    job_name="Wedding Card Run",
    customer="Royal Events",
    time_remaining="about 45 minutes",
    progress="820 of 850 cards printed",
    next_job="Modi pamphlets",
))

print("\n", "=" * 60, "\nAI_REPLY_HEADER\n", "=" * 60)
print(f.AI_REPLY_HEADER.format(first_name="Sharma ji"))

print("\nMeta registry summary:")
print("  total entries:", len(META_TEMPLATES))
print("  bound to Python:", len(bound_templates()))
for k, v in bound_templates().items():
    print(f"    {k} -> {v['python_constant']}")
