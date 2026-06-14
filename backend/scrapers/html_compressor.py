from bs4 import BeautifulSoup
import re


def compress_html(raw_html: str, max_chars: int = 8000) -> str:
    """
    Strips raw HTML to visible text only, capped at max_chars.
    Protects Phi-3 Mini's context window from overflow.
    """
    if not raw_html:
        return ""

    soup = BeautifulSoup(raw_html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "svg"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text)
    lines = [line.strip() for line in text.split(".") if len(line.strip()) > 20]
    text = ". ".join(lines)

    if len(text) > max_chars:
        text = text[:max_chars] + "...[truncated]"

    return text.strip()