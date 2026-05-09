"""Mock-mode smoke for v6.3.18 — confirms the message_formatters shim
routes through the real send pipeline without regressing.

Run from backend/:
    python scripts/smoke_v6_3_18_dispatch.py

Expected output:
  - WHATSAPP_MOCK_MODE = True
  - CLEANED text with no markdown noise
  - One [MOCK SEND] log line at the end
"""

import asyncio
import sys

sys.path.insert(0, ".")

from app.config import settings
from app.services.message_formatters import format_for_whatsapp
from app.services.whatsapp_send import _send_whatsapp_message


def main() -> None:
    print("WHATSAPP_MOCK_MODE =", settings.WHATSAPP_MOCK_MODE)
    if not settings.WHATSAPP_MOCK_MODE:
        print("WARNING: not in mock mode — aborting to avoid a real send.")
        return

    md = (
        "### Today's plan\n"
        "**3 jobs** scheduled, **2 operators** on shift\n"
        "- Bhatia wedding cards\n"
        "- Modi flyers\n"
        "- Patel brochures (continuing)\n"
        "\n"
        "Reply OK to confirm."
    )

    clean = format_for_whatsapp(md)
    print("CLEANED:")
    print(clean)
    print("---")

    asyncio.run(_send_whatsapp_message("+919876543210", clean))


if __name__ == "__main__":
    main()
