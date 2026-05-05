"""
preview_onboarding_message.py - v6.3.12 dev verifier.

Renders the Day-1 onboarding-complete message for all 5 verticals using
stub counts and the default 07:30 morning time. No DB, no backend, no
WHATSAPP_MOCK_MODE required - just exercises the template + label
substitution path so you can eyeball the output.

Usage:
    cd backend
    python tests/smoke/preview_onboarding_message.py
"""

import sys

# PowerShell stdout defaults to cp1252 which can't encode Devanagari.
# Reconfigure to UTF-8 with replacement so the Hindi variant renders
# without crashing. Python 3.7+ feature.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, '.')

from app.services.briefings.templates import INDUSTRY_LABELS, industry_labels
from app.services.whatsapp_responses import RESPONSES, get_response


# Stub values - the actual send pulls these from the DB at message time.
STUB_EMPLOYEE_COUNT = 7
STUB_MACHINE_COUNT = 3
STUB_TIME = "07:30"

# Verticals to preview. Order mirrors INDUSTRY_LABELS for stability.
VERTICALS = list(INDUSTRY_LABELS.keys()) + [None]  # None tests the fallback


def render(industry_type, language="hinglish"):
    labels = industry_labels(industry_type)
    return get_response(
        "onboarding_complete",
        language,
        workspace_label=labels["workspace_label"],
        employee_count=str(STUB_EMPLOYEE_COUNT),
        employees_label=labels["employees"],
        machine_count=str(STUB_MACHINE_COUNT),
        machines_label=labels["machines"],
        time=STUB_TIME,
    )


def main():
    print("=" * 70)
    print("v6.3.12 onboarding-complete message preview")
    print(f"Stub counts: {STUB_EMPLOYEE_COUNT} employees, "
          f"{STUB_MACHINE_COUNT} machines. Time: {STUB_TIME}.")
    print("=" * 70)

    for lang in ("hinglish", "english", "hindi"):
        print(f"\n--- LANGUAGE: {lang} ---")
        for vertical in VERTICALS:
            label_for_print = vertical if vertical is not None else "<None - fallback>"
            print(f"\n  [{label_for_print}]")
            text = render(vertical, language=lang)
            # Indent each line for readability
            for line in text.split("\n"):
                print(f"    {line}")

    # Confirm the template registry has all three locales for this key
    print("\n" + "=" * 70)
    print("Locale coverage check:")
    locales_present = sorted(RESPONSES["onboarding_complete"].keys())
    expected = ["english", "hindi", "hinglish"]
    if locales_present == expected:
        print(f"  PASS: all 3 locales present: {locales_present}")
    else:
        print(f"  FAIL: locales mismatch. expected={expected} got={locales_present}")
    print("=" * 70)


if __name__ == "__main__":
    main()
