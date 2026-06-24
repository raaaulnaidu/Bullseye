"""
rubric_parser.py
----------------
Extracts structured grading criteria from any rubric document (PDF or DOCX).
Uses Claude Haiku (cheap, fast) to parse the rubric into a schema that the
rest of the pipeline can use — RAG retrieval, system prompt, evaluation, dashboard.

The returned schema looks like:
[
  {
    "name":          "Defect Identification",
    "max_points":    30,
    "description":   "Student identifies at least 3 meaningful bugs",
    "keywords":      ["defect", "bug", "issue", "error", "reproduce", ...],
    "section_hints": ["defect", "bug report", "part 2", "2."]
  },
  ...
]

Usage:
    from rubric_parser import parse_rubric
    from document_reader import read_document
    import anthropic

    rubric_text = read_document("path/to/rubric.pdf")
    client = anthropic.Anthropic(api_key="...")
    criteria = parse_rubric(rubric_text, client)
"""

import json
import re
from typing import List, Dict

from memory_layer import file_hash, disk_get, disk_set


_SYSTEM = """You are a rubric parser for an automated grading system.
Extract every grading criterion from the rubric text the user provides.
Return ONLY a valid JSON array — no markdown, no explanation."""

_USER_TEMPLATE = """Extract all grading criteria from this rubric.

For each criterion return:
  name          — short criterion name (3-6 words max)
  max_points    — integer point value (if not shown, distribute 100 equally)
  description   — one sentence describing what is being assessed
  keywords      — 8-12 words/phrases a student would write when addressing this criterion
  section_hints — section headers or labels students typically use (e.g. "part 1", "section 2", "1.")

Return ONLY a JSON array:
[
  {{
    "name": "...",
    "max_points": 0,
    "description": "...",
    "keywords": ["...", "..."],
    "section_hints": ["...", "..."]
  }}
]

RUBRIC TEXT:
{rubric_text}
"""


def _clean_json(raw: str) -> List[Dict]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match:
        cleaned = match.group()
    criteria = json.loads(cleaned)
    for c in criteria:
        c.setdefault("keywords", [])
        c.setdefault("section_hints", [])
        c.setdefault("description", c.get("name", ""))
        c["max_points"] = int(c.get("max_points", 0))
    return criteria


def parse_rubric_openai(rubric_text: str, api_key: str,
                        model: str = "gpt-4o-mini") -> List[Dict]:
    """Parse rubric using OpenAI — use when Anthropic credits are unavailable."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        max_tokens=1500,
        temperature=0,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": _USER_TEMPLATE.format(rubric_text=rubric_text[:6000])},
        ],
    )
    return _clean_json(response.choices[0].message.content.strip())


def parse_rubric_anthropic(rubric_text: str, api_key: str) -> List[Dict]:
    """Parse rubric using Claude Haiku."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system=_SYSTEM,
        messages=[{"role": "user",
                   "content": _USER_TEMPLATE.format(rubric_text=rubric_text[:6000])}],
    )
    return _clean_json(response.content[0].text.strip())


def parse_rubric_cached(rubric_path: str, provider: str = "openai",
                        api_key: str = None,
                        openai_model: str = "gpt-4o-mini") -> List[Dict]:
    """
    Parse a rubric with disk caching. Checks cache first — no API call if
    the same rubric was parsed before.

    Args:
        rubric_path:  Path to rubric PDF or DOCX.
        provider:     'openai' (default) or 'anthropic'.
        api_key:      API key for the chosen provider.
        openai_model: GPT model to use (default gpt-4o-mini).
    """
    from document_reader import read_document

    key = f"rubric_{file_hash(rubric_path)}"
    cached = disk_get(key)
    if cached:
        print("  Rubric: loaded from cache (no API call)")
        return cached

    print(f"  Rubric: parsing with {provider}...")
    rubric_text = read_document(rubric_path)

    if provider == "openai":
        criteria = parse_rubric_openai(rubric_text, api_key, model=openai_model)
    else:
        criteria = parse_rubric_anthropic(rubric_text, api_key)

    disk_set(key, criteria)
    print("  Rubric: cached for future runs")
    return criteria


# Legacy alias — kept so existing CLI scripts don't break
def parse_rubric(rubric_text: str, client) -> List[Dict]:
    raw = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=1500, system=_SYSTEM,
        messages=[{"role": "user",
                   "content": _USER_TEMPLATE.format(rubric_text=rubric_text[:6000])}],
    ).content[0].text.strip()
    return _clean_json(raw)


def criteria_summary(criteria: List[Dict]) -> str:
    """Return a human-readable summary of parsed criteria."""
    total = sum(c["max_points"] for c in criteria)
    lines = [f"  {i+1}. {c['name']} = {c['max_points']} pts" for i, c in enumerate(criteria)]
    lines.append(f"  TOTAL = {total} pts")
    return "\n".join(lines)


def build_rubric_prompt_section(criteria: List[Dict]) -> str:
    """Format criteria for injection into the grader system prompt."""
    total = sum(c["max_points"] for c in criteria)
    lines = []
    for i, c in enumerate(criteria):
        lines.append(f"{i+1}. {c['name']} = {c['max_points']} pts — {c['description']}")
    lines.append(f"\nTOTAL = {total} pts")
    return "\n".join(lines)
