"""AI metadata enrichment (item 2.4).

Proposes description/publisher/language/etc. for books with junk metadata.
Proposals are returned to the caller for confirmation — nothing is written
here. The edit modal pre-fills EMPTY fields only and the user saves
explicitly, so human-edited values are never silently overwritten.
"""

import json
import re

PROMPT = """You are a librarian filling in missing ebook metadata. Based on the
filename and the beginning of the book below, return ONLY a JSON object with
whichever of these keys you can determine confidently:
"title", "author", "publisher", "language" (ISO 639-2 code like "eng"),
"description" (2-4 sentence summary).
Omit keys you are not confident about. No commentary, just JSON.

Filename: {filename}

Book beginning:
{sample}"""

_JSON_RE = re.compile(r"\{.*\}", re.S)

# Only these keys may come back, and each respects its column limit.
_ALLOWED: dict[str, int] = {
    "title": 500,
    "author": 300,
    "publisher": 300,
    "language": 20,
    "description": 20000,
}


def build_prompt(filename: str, sample: str) -> str:
    """Assemble the enrichment prompt."""
    return PROMPT.format(filename=filename, sample=sample[:1200])


def parse_proposals(raw: str) -> dict[str, str]:
    """Extract and sanitize the model's JSON proposal.

    Returns:
        Only allowed keys with non-empty, length-capped string values.
    """
    match = _JSON_RE.search(raw)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    proposals: dict[str, str] = {}
    for key, limit in _ALLOWED.items():
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            proposals[key] = value.strip()[:limit]
    return proposals
