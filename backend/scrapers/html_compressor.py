from bs4 import BeautifulSoup
import re


def compress_html(raw_html: str, max_chars: int = 8000) -> str:
    """
    Strips raw HTML down to only the text content that matters for price extraction.

    WHY THIS EXISTS:
    A full Booking.com or Airbnb page is 200,000+ characters of HTML.
    Sending that to a local LLM (Phi-3 Mini) would overflow its context window
    and produce garbage output. We pre-process it down to ~8,000 characters
    of relevant text — saving inference time and improving accuracy dramatically.

    WHAT WE STRIP:
    - All script and style tags (JS bundles, CSS — useless for price extraction)
    - All HTML tags (keep only visible text)
    - Excessive whitespace (newlines, tabs, multiple spaces)
    - Lines with no useful content (single chars, empty lines)

    WHAT WE KEEP:
    - All visible text content
    - Price-relevant keywords naturally appear in visible text
    """
    soup = BeautifulSoup(raw_html, "lxml")

    # Remove scripts, styles, and hidden elements entirely
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    # Extract visible text
    text = soup.get_text(separator=" ")

    # Collapse all whitespace into single spaces
    text = re.sub(r"\s+", " ", text)

    # Remove lines that are too short to be meaningful
    lines = [line.strip() for line in text.split(".") if len(line.strip()) > 20]
    text = ". ".join(lines)

    # Truncate to max_chars to protect LLM context window
    if len(text) > max_chars:
        text = text[:max_chars] + "...[truncated]"

    return text.strip()