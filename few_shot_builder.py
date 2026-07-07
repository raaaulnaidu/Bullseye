"""
few_shot_builder.py
-------------------
Builds and manages few-shot example sets for the calibrated grader.

Why few-shot failed in Set 4:
  - Examples were injected into the user prompt as text → made the prompt too long
    and confused the JSON output parser.
  - All examples were high-scoring → Claude set an implicit A-grade quality bar
    and everything below it got scored near 0.

How this module fixes it:
  1. Examples are injected as proper Claude conversation turns
     (alternating user/assistant messages BEFORE the real student).
     This is how the Claude API is designed to receive few-shot examples.
  2. Examples span the full grade range: one high (A), one medium (B/C), one low (D/F).
     This anchors Claude's scoring across the whole scale.
  3. Evidence is kept short (RAG chunks only) — no full submissions in examples.

Usage:
    # Auto-build examples from existing graded results
    from few_shot_builder import build_examples_from_results, load_examples, format_as_turns
    import json

    with open("lab01_data/output/all_results.json") as f:
        results = json.load(f)

    examples = build_examples_from_results(results, n_per_band=1)
    save_examples(examples, "lab01_data/output/few_shot_examples.json")

    # Load and use in a grading call
    examples = load_examples("lab01_data/output/few_shot_examples.json")
    turns    = format_as_turns(examples, user_prompt_template)
    # turns is a list of {"role": ..., "content": ...} dicts ready for the API
"""

import json
from pathlib import Path
from typing import List, Dict, Optional


# ── Data structure ─────────────────────────────────────────────────────────────

def make_example(
    student_id: str,
    evidence: str,
    result: dict,
    grade_band: str = "",
) -> dict:
    """
    Create a single few-shot example dict.

    grade_band: "high", "medium", or "low" — used for display only.
    """
    return {
        "student_id": student_id,
        "grade_band": grade_band,
        "evidence":   evidence,
        "result":     result,
    }


# ── Auto-selection from existing results ───────────────────────────────────────

def build_examples_from_results(
    results: List[dict],
    n_per_band: int = 1,
    rag_evidence_map: Optional[Dict[str, str]] = None,
) -> List[dict]:
    """
    Auto-select examples spanning the full grade range from existing graded results.

    Picks:
      - n_per_band examples from high scorers  (≥80% of max)
      - n_per_band examples from medium scorers (50–79%)
      - n_per_band examples from low scorers    (<50%)

    This is the key fix vs Set 4: examples cover all grade levels, not just top students.

    Args:
        results:          List of graded result dicts from all_results.json.
        n_per_band:       How many examples per grade band (default 1, max 2 recommended).
        rag_evidence_map: Optional {student_id: evidence_text} — if provided, the
                          actual RAG evidence used during grading is stored in the example.
                          If omitted, a summary from the criteria feedback is used instead.

    Returns:
        List of example dicts ready to save or pass to format_as_turns().
    """
    if not results:
        return []

    max_score = results[0].get("max_score", 20)

    def pct(r):
        return r.get("total_score", 0) / max_score * 100 if max_score else 0

    high   = sorted([r for r in results if pct(r) >= 80],  key=pct, reverse=True)
    medium = sorted([r for r in results if 50 <= pct(r) < 80], key=lambda r: abs(pct(r) - 65))
    low    = sorted([r for r in results if pct(r) < 50],   key=pct)

    selected = []
    for band_name, band_list in [("high", high), ("medium", medium), ("low", low)]:
        for r in band_list[:n_per_band]:
            sid = r.get("student_id", "")
            evidence = (
                rag_evidence_map.get(sid, "")
                if rag_evidence_map
                else _evidence_from_feedback(r)
            )
            clean = _strip_calibration(r)
            selected.append(make_example(
                student_id=sid,
                evidence=evidence,
                result=clean,
                grade_band=band_name,
            ))

    return selected


def _evidence_from_feedback(result: dict) -> str:
    """
    Build a short evidence summary from the criteria feedback when the original
    RAG evidence text is not available. Used as a fallback.
    """
    lines = []
    for c in result.get("criteria", []):
        completed = c.get("completed", "").strip()
        missing   = c.get("missing_or_weak", "").strip()
        if completed:
            lines.append(f"[{c['name']}] {completed}")
        elif missing:
            lines.append(f"[{c['name']}] (no evidence found — {missing})")
    return "\n".join(lines) if lines else "(no evidence)"


def _strip_calibration(result: dict) -> dict:
    """
    Return a clean copy of the result for use as a few-shot target,
    using raw (pre-calibration) scores so the example doesn't encode
    the offset twice when calibration is applied to the real student.
    """
    import copy
    r = copy.deepcopy(result)
    # Use raw scores if available (before calibration offset was applied)
    if "total_score_raw" in r:
        r["total_score"] = r.pop("total_score_raw")
    for c in r.get("criteria", []):
        if "awarded_points_raw" in c:
            c["awarded_points"] = c.pop("awarded_points_raw")
    # Remove pipeline metadata — not useful in examples
    for key in ["calibration_offset_applied", "rubric_criteria", "assignment_name"]:
        r.pop(key, None)
    return r


# ── Persistence ────────────────────────────────────────────────────────────────

def save_examples(examples: List[dict], path: str) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(examples, f, indent=2)
    return path


def load_examples(path: str) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Conversation turn formatter ────────────────────────────────────────────────

def format_as_turns(
    examples: List[dict],
    user_prompt_template: str,
    instructions_text: str = "",
) -> List[Dict[str, str]]:
    """
    Convert examples into Claude conversation turns for few-shot prompting.

    Returns a list of {"role": "user"|"assistant", "content": "..."} dicts.
    These go BEFORE the real student's message in the messages array.

    Structure:
        [
          {"role": "user",      "content": "<example 1 prompt>"},
          {"role": "assistant", "content": "<example 1 JSON result>"},
          {"role": "user",      "content": "<example 2 prompt>"},
          {"role": "assistant", "content": "<example 2 JSON result>"},
          ... (real student added by caller)
        ]

    The assistant turns contain ONLY the clean JSON — no preamble — so Claude
    learns the exact output format as well as the scoring calibration.
    """
    turns = []
    for ex in examples:
        user_content = user_prompt_template.format(
            instructions=instructions_text[:1000],  # shorter in examples
            rag_evidence=ex.get("evidence", "(no evidence)"),
            submission_context=ex.get("evidence", "(example context omitted)"),
            evidence_mode="few_shot_example",
        )
        # Prefix with grade band hint so Claude understands the score level
        band = ex.get("grade_band", "")
        band_note = f"[Example — {band} grade]\n" if band else "[Example]\n"
        turns.append({"role": "user",      "content": band_note + user_content})
        turns.append({"role": "assistant", "content": json.dumps(ex["result"], indent=2)})
    return turns


# ── Summary ────────────────────────────────────────────────────────────────────

def summarize_examples(examples: List[dict]) -> str:
    lines = [f"  {len(examples)} few-shot example(s):"]
    for ex in examples:
        sid   = ex.get("student_id", "?")
        band  = ex.get("grade_band", "?")
        total = ex.get("result", {}).get("total_score", "?")
        max_s = ex.get("result", {}).get("max_score", "?")
        lines.append(f"    [{band:>6}]  {sid}  score={total}/{max_s}")
    return "\n".join(lines)
