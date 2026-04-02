import re
import logging

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FORMATTING CONSTANTS - all limits defined here, never buried in functions
# ---------------------------------------------------------------------------

# Maximum characters in a single WhatsApp message.
# WhatsApp hard limit is 4096 but long messages are hard to read on mobile.
# We truncate at 1500 and add a "reply MORE for full details" hint.
MAX_MESSAGE_LENGTH = 1500

# The text appended when a response is truncated.
# Written in Hinglish so it works for all language modes.
TRUNCATION_SUFFIX = "\n\n... (poora jawaab ke liye reply karein: MORE)"

# WhatsApp supports these formatting markers but we strip them for clarity.
# Factory owners on mobile find raw markdown symbols confusing.
BULLET_REPLACEMENT = "• "   # Replace markdown - bullets with proper bullet character


# ---------------------------------------------------------------------------
# MAIN FUNCTION - format_for_whatsapp()
# ---------------------------------------------------------------------------

def format_for_whatsapp(text: str) -> str:
    """
    Convert a markdown-formatted AI response to WhatsApp-safe plain text.

    This is the only function most callers need. It runs all formatting
    steps in the correct order and returns a clean string ready to send.

    The order of operations matters — for example, headers must be
    processed before bold markers because ### headers also contain text
    that might be bolded.

    Args:
        text: Raw AI response string, may contain markdown formatting.
              Can be empty string or None — both handled safely.

    Returns:
        Cleaned plain text string safe to send via WhatsApp.
        Never returns None — always returns a string.
        If input is empty or None, returns a fallback message.

    Side effects:
        None — pure function, no external calls, no state changes.
        Logs a warning if the response was truncated.
    """

    # Guard: handle empty or None input gracefully.
    # This can happen if the AI returns an empty response.
    if not text or not text.strip():
        logger.warning(
            "format_for_whatsapp received empty text. "
            "The AI returned an empty response. "
            "Check run_ai_chat() for errors upstream."
        )
        return "Maafi kijiye, kuch gadbad ho gayi. Dobara try karein."
        # Translation: "Sorry, something went wrong. Please try again."

    # Run all formatting steps in order.
    # Each step is a separate function so it can be tested independently.
    text = _remove_code_blocks(text)
    text = _remove_headers(text)
    text = _remove_bold_markers(text)
    text = _remove_italic_markers(text)
    text = _convert_bullet_points(text)
    text = _convert_numbered_lists(text)
    text = _convert_markdown_tables(text)
    text = _clean_extra_whitespace(text)
    text = _truncate_if_too_long(text)

    return text.strip()


# ---------------------------------------------------------------------------
# PRIVATE FORMATTING STEPS - each does exactly one transformation
# ---------------------------------------------------------------------------

def _remove_code_blocks(text: str) -> str:
    """
    Remove markdown code blocks (``` ... ```) and inline code (`code`).

    Code blocks appear when the AI formats data as tables or lists
    using triple backticks. On WhatsApp these show as raw backtick
    characters which look like noise to a factory owner.

    Args:
        text: Input text possibly containing ``` code blocks ```

    Returns:
        Text with code block markers removed. Content inside the
        blocks is kept — just the backtick markers are stripped.

    Example:
        Input:  "Result:\n```\nJob 1: Printing\nJob 2: Cutting\n```"
        Output: "Result:\nJob 1: Printing\nJob 2: Cutting"
    """
    # Remove triple backtick blocks - including the optional language hint
    # e.g. ```python or ```json after the opening backticks
    # re.DOTALL makes . match newlines too - needed for multi-line blocks
    text = re.sub(r"```[a-zA-Z]*\n?", "", text, flags=re.DOTALL)
    text = re.sub(r"```", "", text)

    # Remove single backtick inline code markers
    # e.g. `tenant_id` becomes tenant_id
    text = re.sub(r"`([^`]+)`", r"\1", text)

    return text


def _remove_headers(text: str) -> str:
    """
    Convert markdown headers (###, ##, #) to plain text with a newline before.

    Headers like ### Today's Schedule become plain text.
    We add a newline before the header text so it still stands out
    visually as a section start, just without the # symbols.

    Args:
        text: Input text possibly containing # header markers.

    Returns:
        Text with # markers removed, newline added before header text.

    Example:
        Input:  "### Today's Schedule\nJob 1..."
        Output: "\nToday's Schedule\nJob 1..."
    """
    # Match 1-6 # characters at start of line followed by a space
    # Replace with newline + the header text (no # symbols)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\n\1", text, flags=re.MULTILINE)
    return text


def _remove_bold_markers(text: str) -> str:
    """
    Remove markdown bold markers (**text** and __text__).

    Bold markers look like this to a factory owner on WhatsApp:
    **Ravi Kumar** — the asterisks show as raw characters.
    We strip the markers and keep the text.

    Args:
        text: Input text possibly containing **bold** markers.

    Returns:
        Text with ** and __ markers removed, bold text kept as plain text.

    Example:
        Input:  "**3 jobs scheduled** for today"
        Output: "3 jobs scheduled for today"
    """
    # Remove ** bold markers (most common in AI responses)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)

    # Remove __ bold markers (less common but possible)
    text = re.sub(r"__(.+?)__", r"\1", text)

    return text


def _remove_italic_markers(text: str) -> str:
    """
    Remove markdown italic markers (*text* and _text_).

    Single asterisk or underscore around text = italic in markdown.
    On WhatsApp these show as raw symbols.

    Args:
        text: Input text possibly containing *italic* markers.

    Returns:
        Text with * and _ italic markers removed, text kept.

    Example:
        Input:  "Job status: *delayed*"
        Output: "Job status: delayed"

    Note:
        This runs AFTER _remove_bold_markers() intentionally.
        Bold (**) must be removed first, otherwise the single * regex
        would partially match ** and produce malformed output.
    """
    # Remove single * italic markers
    # [^*] ensures we only match single asterisks, not double ones
    text = re.sub(r"\*([^*\n]+?)\*", r"\1", text)

    # Remove single _ italic markers
    # We are careful not to match underscores in variable names like tenant_id
    # The word boundary \b prevents matching mid-word underscores
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"\1", text)

    return text


def _convert_bullet_points(text: str) -> str:
    """
    Convert markdown bullet points (- item) to WhatsApp bullet character (• item).

    Markdown uses a hyphen-space at the start of a line for bullets.
    We replace this with the proper bullet character •  which is
    universally supported in WhatsApp on all devices.

    Args:
        text: Input text possibly containing - bullet points.

    Returns:
        Text with - bullets replaced by • bullets.

    Example:
        Input:  "Jobs today:\n- Job 1: Printing\n- Job 2: Cutting"
        Output: "Jobs today:\n• Job 1: Printing\n• Job 2: Cutting"
    """
    # Match hyphen-space at the start of a line (markdown bullet format)
    # ^ with MULTILINE matches start of each line, not just start of string
    text = re.sub(r"^- ", BULLET_REPLACEMENT, text, flags=re.MULTILINE)

    # Also handle indented bullets (  - item) - common in nested lists
    text = re.sub(r"^\s{2,}- ", BULLET_REPLACEMENT, text, flags=re.MULTILINE)

    return text


def _convert_numbered_lists(text: str) -> str:
    """
    Keep numbered lists (1. item) but clean up extra spacing around them.

    Numbered lists are fine in WhatsApp — we keep the numbers.
    We just ensure there is no extra indentation that would look odd
    on a mobile screen.

    Args:
        text: Input text possibly containing numbered list items.

    Returns:
        Text with numbered list items left-aligned, no leading spaces.

    Example:
        Input:  "Steps:\n   1. First step\n   2. Second step"
        Output: "Steps:\n1. First step\n2. Second step"
    """
    # Remove leading whitespace before numbered list items
    text = re.sub(r"^\s+(\d+\.)", r"\1", text, flags=re.MULTILINE)
    return text


def _convert_markdown_tables(text: str) -> str:
    """
    Convert markdown tables to simple line-by-line plain text.

    Markdown tables use | pipe characters and --- separator rows.
    These render as unreadable noise on WhatsApp mobile.
    We convert each data row to a simple "Key: Value" line format.

    Args:
        text: Input text possibly containing | markdown tables |

    Returns:
        Text with markdown tables converted to plain text lines.

    Example:
        Input:
            | Job    | Status  |
            |--------|---------|
            | Job 1  | Running |
            | Job 2  | Done    |

        Output:
            Job | Status
            Job 1 | Running
            Job 2 | Done
    """
    lines = text.split("\n")
    result_lines = []

    for line in lines:
        # Detect separator rows like |---|---| or |:--|--:|
        # These are table dividers - skip them entirely
        if re.match(r"^\s*\|[-:\s|]+\|\s*$", line):
            continue

        # Detect table data rows - lines starting and ending with |
        if line.strip().startswith("|") and line.strip().endswith("|"):
            # Extract cell contents by splitting on | and cleaning whitespace
            cells = [cell.strip() for cell in line.split("|")]
            # Filter out empty strings from leading/trailing | characters
            cells = [c for c in cells if c]
            if cells:
                # Join cells with | separator - readable on mobile
                result_lines.append(" | ".join(cells))
            continue

        # Not a table line - keep as-is
        result_lines.append(line)

    return "\n".join(result_lines)


def _clean_extra_whitespace(text: str) -> str:
    """
    Remove excessive blank lines and trailing spaces.

    AI responses often have multiple consecutive blank lines between
    sections. On mobile, this wastes screen space. We collapse
    multiple blank lines into a single blank line.

    Args:
        text: Input text possibly containing excessive whitespace.

    Returns:
        Text with multiple consecutive blank lines reduced to one,
        and trailing spaces removed from each line.

    Example:
        Input:  "Line 1\n\n\n\nLine 2"
        Output: "Line 1\n\nLine 2"
    """
    # Remove trailing spaces from each line
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)

    # Collapse 3 or more consecutive newlines into exactly 2 (one blank line)
    # This preserves intentional paragraph breaks while removing excessive gaps
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


def _truncate_if_too_long(text: str) -> str:
    """
    Truncate responses that exceed MAX_MESSAGE_LENGTH characters.

    Very long AI responses are hard to read on mobile. We cut at
    MAX_MESSAGE_LENGTH and add a hint telling the owner they can
    request the full response by replying MORE.

    We truncate at a sentence boundary when possible — cutting mid-sentence
    is jarring. We look for the last sentence-ending punctuation (. ! ?)
    within the allowed length and cut there.

    Args:
        text: Input text of any length.

    Returns:
        Original text if within limit.
        Truncated text with suffix appended if over limit.

    Example:
        A 2000-character response gets cut to ~1500 characters
        with "... (poora jawaab ke liye reply karein: MORE)" appended.
    """
    # Check if truncation is needed at all
    if len(text) <= MAX_MESSAGE_LENGTH:
        return text

    # Find a good cut point - look for sentence end near the limit.
    # We search in the last 200 characters of the allowed window.
    search_start = MAX_MESSAGE_LENGTH - 200
    search_window = text[search_start:MAX_MESSAGE_LENGTH]

    # Find the last sentence-ending punctuation in the search window
    last_sentence_end = max(
        search_window.rfind(". "),
        search_window.rfind("! "),
        search_window.rfind("? "),
        search_window.rfind(".\n"),
    )

    if last_sentence_end != -1:
        # Cut at the sentence boundary for a cleaner break
        cut_point = search_start + last_sentence_end + 1
    else:
        # No sentence boundary found - cut at the hard limit
        cut_point = MAX_MESSAGE_LENGTH

    truncated = text[:cut_point].rstrip()

    logger.info(
        f"Response truncated from {len(text)} to {len(truncated)} characters. "
        f"Owner can reply MORE to request full response."
    )

    # Append the truncation hint in Hinglish
    return truncated + TRUNCATION_SUFFIX


# ---------------------------------------------------------------------------
# UTILITY FUNCTION - detect_language()
# ---------------------------------------------------------------------------

def detect_language(text: str) -> str:
    """
    Detect whether a message is Hindi, Hinglish, or English.

    Used to determine how the AI should respond — it should match
    the owner's language style. Also stored in whatsapp_conversations
    for Factory GPT training data segmentation.

    Detection logic:
      - If any Devanagari Unicode characters present → 'hindi'
      - If common Hinglish words present → 'hinglish'
      - Otherwise → 'english'

    This is a simple heuristic, not an NLP model. It is fast and
    works well for the Hindi/Hinglish/English mix used by Indian
    MSME factory owners.

    Args:
        text: The raw message text from the factory owner.

    Returns:
        'hindi'    — message contains Devanagari script
        'hinglish' — message uses Hindi words in Latin script
        'english'  — message is primarily English

    Side effects:
        None — pure function.
    """

    # Check for Devanagari Unicode block (U+0900 to U+097F)
    # Any character in this range = Hindi script
    if re.search(r"[\u0900-\u097F]", text):
        return "hindi"

    # Common Hinglish words - Hindi spoken in Latin script.
    # Factory owners frequently use these when typing on a phone.
    # We check lowercase to make matching case-insensitive.
    hinglish_words = [
        "aaj", "kal", "kya", "hai", "hain", "nahi", "nahin",
        "karo", "karo", "kab", "kaun", "kahan", "kitna", "kitne",
        "bahut", "thoda", "abhi", "jaldi", "theek", "accha",
        "bata", "dekho", "lao", "do", "ho", "gaya", "gayi",
        "schedule", "kaam", "kab", "banda", "log", "machine",
        "haan", "naya", "purana", "zyada", "kam"
    ]

    text_lower = text.lower()

    # Count how many Hinglish words appear in the message
    hinglish_count = sum(
        1 for word in hinglish_words
        # Use word boundary matching to avoid partial matches
        # e.g. "kam" should not match "kamra"
        if re.search(r"\b" + word + r"\b", text_lower)
    )

    # If 2 or more Hinglish words found, classify as Hinglish
    # Threshold of 2 avoids false positives from single common words
    if hinglish_count >= 2:
        return "hinglish"

    # Default - treat as English
    return "english"