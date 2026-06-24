"""
calibrated_grader.py
--------------------
Privacy-aware, RAG-calibrated grading pipeline — works with ANY assignment and rubric.

Steps per student:
  1. Anonymize submission locally (names, IDs, emails stripped before any API call).
  2. Extract rubric-relevant evidence chunks via keyword RAG (reduces token usage).
  3. Send only the evidence + dynamic rubric to Claude for grading.
  4. Apply a calibration offset to close the observed AI–human scoring gap.

Usage (interactive):
    python calibrated_grader.py

Usage (command-line):
    python calibrated_grader.py \\
        --instructions path/to/instructions.pdf \\
        --rubric       path/to/rubric.pdf \\
        --submissions  path/to/submissions_folder/ \\
        --output       path/to/output_folder/ \\
        --assignment   "ISM 6145 — Testing Assignment 1"
"""

from pathlib import Path
import os

env_path = Path(".env")
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()

import argparse
import json
import re
import time
from typing import List, Dict

import anthropic
import httpx


# ── Ollama client (OpenAI-compatible, uses httpx — no extra packages needed) ──

class OllamaClient:
    """
    Thin wrapper around Ollama's REST API using httpx.
    Mirrors the subset of the Anthropic client interface used by CalibratedGrader.
    """
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=300)

    def create(self, model: str, system: str, messages: List[Dict], max_tokens: int = 2500) -> str:
        """Send a chat request and return the response text."""
        # Ollama uses OpenAI format: system goes as first message
        ollama_messages = [{"role": "system", "content": system}] + messages
        payload = {
            "model":      model,
            "messages":   ollama_messages,
            "stream":     False,
            "options":    {"num_predict": max_tokens},
        }
        resp = self._http.post(f"{self.base_url}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()

    @classmethod
    def check_connection(cls, base_url: str = "http://localhost:11434") -> bool:
        try:
            r = httpx.get(f"{base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    @classmethod
    def list_models(cls, base_url: str = "http://localhost:11434") -> List[str]:
        try:
            r = httpx.get(f"{base_url}/api/tags", timeout=3)
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []


# ── OpenAI client ─────────────────────────────────────────────────────────────

class OpenAIClient:
    """
    Thin wrapper around the OpenAI Chat Completions API.
    Supports GPT-4o, GPT-4o-mini, GPT-4-turbo, GPT-3.5-turbo.
    """
    def __init__(self, api_key: str):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Run: pip install openai")
        self._client = OpenAI(api_key=api_key)

    def create(self, model: str, system: str, messages: List[Dict], max_tokens: int = 2500) -> str:
        oai_messages = [{"role": "system", "content": system}] + messages
        response = self._client.chat.completions.create(
            model=model,
            messages=oai_messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    @classmethod
    def check_key(cls, api_key: str) -> bool:
        try:
            from openai import OpenAI
            OpenAI(api_key=api_key).models.list()
            return True
        except Exception:
            return False


# ── Hugging Face Inference API client ─────────────────────────────────────────

# Default free models known to follow JSON instructions reliably
HF_RECOMMENDED_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "meta-llama/Llama-3.1-8B-Instruct",
    "HuggingFaceH4/zephyr-7b-beta",
]

class HuggingFaceClient:
    """
    Thin wrapper around the Hugging Face Inference API (serverless, free tier).
    Uses huggingface_hub.InferenceClient — no GPU or local install needed.
    Models run on HF's servers; data leaves the machine (same as Anthropic API).
    """
    def __init__(self, model: str, token: str):
        try:
            from huggingface_hub import InferenceClient
        except ImportError:
            raise ImportError("Run: pip install huggingface_hub")
        self._client = InferenceClient(model=model, token=token)
        self.model   = model

    def create(self, model: str, system: str, messages: List[Dict], max_tokens: int = 2500) -> str:
        hf_messages = [{"role": "system", "content": system}] + messages
        response = self._client.chat_completion(
            model=model or self.model,
            messages=hf_messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    @classmethod
    def check_token(cls, token: str) -> bool:
        try:
            from huggingface_hub import whoami
            whoami(token=token)
            return True
        except Exception:
            return False


from document_reader import read_document, load_student_submissions
from privacy_processor import anonymize
from rag_retriever import build_rag_evidence, build_rag_evidence_semantic
from rubric_parser import parse_rubric_cached, criteria_summary, build_rubric_prompt_section
from evaluator import create_gold_standard_template
from few_shot_builder import (
    build_examples_from_results, save_examples, load_examples,
    format_as_turns, summarize_examples,
)
from memory_layer import session_get, session_set, text_hash


# ── Scoring band defaults ─────────────────────────────────────────────────────
# Each value is the LOWER bound of that band.
# Upper bound is computed automatically as: next band's lower - 1 (top band caps at 100).
# Override any value via CLI: --pct-full 98 --pct-good 95 --pct-partial 87 --pct-attempt 40
SCORING_DEFAULTS = {
    "pct_full":    98,  # 98–100%  everything correct
    "pct_good":    95,  # 95–97%   mostly correct, one gap
    "pct_partial": 87,  # 87–94%   attempted, multiple gaps
    "pct_attempt": 40,  # 40–86%   very thin or largely wrong
    #                     0%        completely absent
}


def _build_system_prompt(assignment_name: str, rubric_section: str,
                         max_score: int, bands: dict = None,
                         local_model: bool = False) -> str:
    b = {**SCORING_DEFAULTS, **(bands or {})}
    r_full    = f"{b['pct_full']}–100%"
    r_good    = f"{b['pct_good']}–{b['pct_full'] - 1}%"
    r_partial = f"{b['pct_partial']}–{b['pct_good'] - 1}%"
    r_attempt = f"{b['pct_attempt']}–{b['pct_partial'] - 1}%"

    if local_model:
        # Fix 3 — shorter, more direct prompt for small local models
        return f"""You are a TA grading undergraduate submissions. Grade leniently — reward effort.

SCORING (use % of each criterion's max_points):
- {r_full}: correct and complete
- {r_good}: mostly correct, one gap
- {r_partial}: attempted but multiple gaps
- {r_attempt}: very thin or largely wrong
- 0%: completely absent

RULES: never deduct for style/formatting. When unsure, pick the higher score.

Assignment: {assignment_name}
Rubric:
{rubric_section}

You MUST return ONLY this exact JSON structure — no extra text, no markdown:
{{
  "student_id": "",
  "total_score": 0,
  "max_score": {max_score},
  "percentage": 0.0,
  "criteria": [
    {{
      "name": "<exact criterion name from rubric>",
      "max_points": 0,
      "awarded_points": 0,
      "completed": "<one sentence>",
      "missing_or_weak": "<one sentence>",
      "suggestion": "<one sentence>"
    }}
  ],
  "overall_feedback": "<two sentences>",
  "consistency_notes": ""
}}
"""

    return f"""You are a Teaching Assistant grading undergraduate student submissions for an AI for Analytics course.

Grade fairly and consistently — like an experienced human TA who rewards effort and intent.

SCORING BANDS (apply per criterion using its max_points):

  FULL MARKS  ({r_full} of criterion points)
    Content is present and correct. Minor typos, informal phrasing, or small
    formatting issues are acceptable and must NOT reduce the score.

  GOOD ATTEMPT  ({r_good} of criterion points)
    Content is mostly correct but one specific component is missing or slightly off.
    Deduct only for that specific gap — nothing else.

  PARTIAL CREDIT  ({r_partial} of criterion points)
    Student attempted the section but multiple required components are missing or incorrect.
    Be specific about what is wrong. Do NOT penalise for style or language.

  MINIMAL ATTEMPT  ({r_attempt} of criterion points)
    Student wrote something relevant but it is largely incorrect, very shallow, or off-track.

  ZERO  (0 points)
    Section is completely absent from the submission, or response is entirely off-topic.

RULES:
  - Never deduct for formatting, informal language, or writing style.
  - Never count the same issue against more than one criterion.
  - When uncertain between two bands, always choose the HIGHER one.
  - Apply the same standard to every student.
  - Grade ONLY the evidence provided.

Assignment: {assignment_name}

Rubric:
{rubric_section}

For EACH criterion:
1. State what was completed (based on the provided evidence)
2. State what is missing or weak (name the specific missing component)
3. Give ONE improvement suggestion

Return ONLY valid JSON — no markdown fences, no extra text.

JSON FORMAT:
{{
  "student_id": "",
  "total_score": 0,
  "max_score": {max_score},
  "percentage": 0.0,
  "criteria": [
    {{
      "name": "",
      "max_points": 0,
      "awarded_points": 0,
      "completed": "",
      "missing_or_weak": "",
      "suggestion": ""
    }}
  ],
  "overall_feedback": "",
  "consistency_notes": ""
}}
"""

_USER_TEMPLATE = """
ASSIGNMENT INSTRUCTIONS:
{instructions}

RUBRIC-EXTRACTED EVIDENCE:
(Only the most relevant portions of the student's anonymized submission
are shown below, organized by rubric criterion.)

{rag_evidence}

Evaluate ONLY the evidence shown above. If a criterion's evidence section
is empty or unclear, award 0 and explain what was expected.
Return ONLY JSON.
"""


# ── Fix 2: few-shot example for local models ──────────────────────────────────

def _build_local_fewshot(criteria: List[Dict]) -> List[Dict]:
    """
    Returns a user+assistant message pair showing the exact JSON schema.
    Local models (7B and below) follow format much better after seeing one example.
    The example uses 90% scores so the model learns to grade generously.
    """
    example_criteria = [
        {
            "name": c["name"],
            "max_points": c["max_points"],
            "awarded_points": round(c["max_points"] * 0.9),
            "completed": "Student addressed this section with appropriate content.",
            "missing_or_weak": "Minor detail could be more specific.",
            "suggestion": "Add one concrete example to strengthen this section.",
        }
        for c in criteria
    ]
    total   = sum(c["awarded_points"] for c in example_criteria)
    max_s   = sum(c["max_points"]     for c in criteria)
    example = json.dumps({
        "student_id":       "",
        "total_score":      total,
        "max_score":        max_s,
        "percentage":       round(total / max_s * 100, 1),
        "criteria":         example_criteria,
        "overall_feedback": "Good effort overall. Student addressed most requirements with reasonable depth.",
        "consistency_notes": "",
    }, indent=2)
    return [
        {"role": "user",      "content": "Grade this sample submission. Return only JSON."},
        {"role": "assistant", "content": example},
    ]


# ── Fix 1: robust JSON parser with schema repair ───────────────────────────────

def _parse_json_response(raw_text: str, criteria: List[Dict], max_score: int) -> dict:
    """
    Parse the model's grading response with automatic repair for non-standard formats.

    Handles:
    - Markdown code fences (```json ... ```)
    - Qwen-style "Criterion 1": {"score": X} output instead of a criteria array
    - Missing / wrong total_score (recomputed from awarded_points)
    - Complete parse failure (returns zeroed result with note)
    """
    # Strip markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$",          "", cleaned,   flags=re.MULTILINE)
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        cleaned = m.group()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        return _empty_result(criteria, max_score, note="Model output could not be parsed as JSON.")

    # Standard schema — recompute total in case model arithmetic was wrong
    if "criteria" in result and isinstance(result["criteria"], list) and result["criteria"]:
        total = sum(float(c.get("awarded_points", 0)) for c in result["criteria"])
        result["total_score"] = round(total, 1)
        result["percentage"]  = round(total / max_score * 100, 1) if max_score else 0.0
        return result

    # Non-standard schema repair — map whatever the model returned to expected criteria
    repaired = []
    for i, c in enumerate(criteria):
        awarded      = None
        feedback_txt = ""

        # Try the key patterns small models commonly use
        for key in [
            f"Criterion {i+1}", f"criterion_{i+1}", f"criterion{i+1}",
            c["name"], c["name"].lower(), c["name"].replace(" ", "_").lower(),
        ]:
            if key in result:
                val = result[key]
                if isinstance(val, dict):
                    awarded      = val.get("score") or val.get("awarded_points") or val.get("points") or 0
                    feedback_txt = str(val.get("feedback") or val.get("comment") or "")
                elif isinstance(val, (int, float)):
                    awarded = val
                break

        awarded = min(float(awarded or 0), c["max_points"])
        repaired.append({
            "name":            c["name"],
            "max_points":      c["max_points"],
            "awarded_points":  round(awarded, 1),
            "completed":       feedback_txt[:200] or "See model response.",
            "missing_or_weak": "",
            "suggestion":      "",
        })

    total = sum(c["awarded_points"] for c in repaired)
    return {
        "total_score":      round(total, 1),
        "max_score":        max_score,
        "percentage":       round(total / max_score * 100, 1) if max_score else 0.0,
        "criteria":         repaired,
        "overall_feedback": result.get("overall_feedback", ""),
        "consistency_notes": "Score recovered from non-standard model output format.",
    }


def _empty_result(criteria: List[Dict], max_score: int, note: str = "") -> dict:
    return {
        "total_score":      0,
        "max_score":        max_score,
        "percentage":       0.0,
        "criteria":         [
            {"name": c["name"], "max_points": c["max_points"], "awarded_points": 0,
             "completed": "", "missing_or_weak": "Parse error", "suggestion": ""}
            for c in criteria
        ],
        "overall_feedback":  note,
        "consistency_notes": "Failed to parse model output.",
    }


# ── Grader class ──────────────────────────────────────────────────────────────

class CalibratedGrader:
    def __init__(
        self,
        criteria: List[Dict],
        assignment_name: str = "Assignment",
        model: str = "claude-sonnet-4-6",
        calibration_offset: float = 0.0,
        few_shot_examples: List[Dict] = None,
        provider: str = "anthropic",
        api_key: str = None,
        ollama_url: str = "http://localhost:11434",
        rag_mode: str = "keyword",
        scoring_bands: dict = None,
    ):
        self.provider = provider
        self.model    = model
        self.criteria = criteria
        self.assignment_name = assignment_name
        self.max_score = sum(c["max_points"] for c in criteria)
        self.calibration_offset = calibration_offset
        self.few_shot_examples  = few_shot_examples or []
        self.rag_mode = rag_mode

        if provider == "ollama":
            self.client = OllamaClient(base_url=ollama_url)
        elif provider == "huggingface":
            self.client = HuggingFaceClient(model=model, token=api_key)
        elif provider == "openai":
            self.client = OpenAIClient(api_key=api_key)
        else:
            self.client = anthropic.Anthropic(api_key=api_key)

        self.system_prompt = _build_system_prompt(
            assignment_name=assignment_name,
            rubric_section=build_rubric_prompt_section(criteria),
            max_score=self.max_score,
            bands=scoring_bands,
            local_model=(provider in ("ollama", "huggingface")),
        )

    def grade_submission(
        self,
        instructions_text: str,
        submission_text: str,
        student_id: str,
        student_name: str = "",
    ) -> dict:
        """
        Grade a single submission using the privacy-aware RAG pipeline.

        Steps:
          1. Anonymize the submission locally.
          2. Extract rubric-relevant evidence chunks (RAG).
          3. Send only the evidence to Claude with the dynamic rubric.
          4. Parse and return the structured JSON result.
          5. Apply calibration offset to close the AI–human scoring gap.
        """
        # Step 1 — anonymize locally (short-term cache: skip if same text seen this session)
        anon_cache_key = f"anon_{text_hash(submission_text)}"
        anon_text = session_get(anon_cache_key)
        if anon_text is None:
            anon_text, anon_log = anonymize(submission_text, known_name=student_name)
            session_set(anon_cache_key, anon_text)
            if anon_log:
                print(f"    [privacy] {student_id}: {', '.join(anon_log)}")

        # Step 2 — RAG evidence (short-term cache + keyword or semantic mode)
        rag_cache_key = f"rag_{self.rag_mode}_{text_hash(anon_text)}"
        rag_evidence = session_get(rag_cache_key)
        if rag_evidence is None:
            if self.rag_mode == "semantic":
                rag_evidence = build_rag_evidence_semantic(anon_text, criteria=self.criteria, top_n=3)
            else:
                rag_evidence = build_rag_evidence(anon_text, criteria=self.criteria, top_n=3)
            session_set(rag_cache_key, rag_evidence)

        # Step 3 — build messages
        student_prompt = _USER_TEMPLATE.format(
            instructions=instructions_text[:3000],
            rag_evidence=rag_evidence,
        )

        messages = []
        if self.provider in ("ollama", "huggingface"):
            # Inline few-shot example so small/open models see the exact JSON schema
            messages += _build_local_fewshot(self.criteria)
        elif self.few_shot_examples:
            messages += format_as_turns(
                self.few_shot_examples,
                _USER_TEMPLATE,
                instructions_text,
            )
        messages.append({"role": "user", "content": student_prompt})

        if self.provider in ("ollama", "huggingface", "openai"):
            raw_text = self.client.create(
                model=self.model,
                system=self.system_prompt,
                messages=messages,
                max_tokens=2500,
            )
        else:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2500,
                system=self.system_prompt,
                messages=messages,
            )
            raw_text = response.content[0].text.strip()

        # Step 4 — parse JSON with robust repair fallback
        result = _parse_json_response(raw_text, self.criteria, self.max_score)
        result["student_id"] = student_id
        result["max_score"] = self.max_score
        result["assignment_name"] = self.assignment_name
        result["rubric_criteria"] = self.criteria

        # Step 5 — apply calibration offset
        if self.calibration_offset != 0:
            result = self._apply_calibration(result)

        return result

    def _apply_calibration(self, result: dict) -> dict:
        """
        Distribute calibration_offset proportionally across criteria, capped at max_points.
        Stores raw scores alongside calibrated scores for transparency.
        """
        max_score = result.get("max_score", self.max_score)
        criteria = result.get("criteria", [])
        criteria_max_total = sum(c.get("max_points", 0) for c in criteria)

        for c in criteria:
            cmax = c.get("max_points", 0)
            proportional = self.calibration_offset * (cmax / criteria_max_total) if criteria_max_total > 0 else 0
            raw = c.get("awarded_points", 0)
            c["awarded_points"] = round(min(cmax, raw + proportional), 1)
            c["awarded_points_raw"] = raw

        raw_total = result.get("total_score", 0)
        calibrated_total = round(min(max_score, raw_total + self.calibration_offset), 1)
        result["total_score"] = calibrated_total
        result["total_score_raw"] = raw_total
        result["calibration_offset_applied"] = self.calibration_offset
        result["percentage"] = round((calibrated_total / max_score) * 100, 1)

        pct = result["percentage"]
        if pct >= 93:   result["letter_grade"] = "A"
        elif pct >= 90: result["letter_grade"] = "A-"
        elif pct >= 87: result["letter_grade"] = "B+"
        elif pct >= 83: result["letter_grade"] = "B"
        elif pct >= 80: result["letter_grade"] = "B-"
        elif pct >= 77: result["letter_grade"] = "C+"
        elif pct >= 73: result["letter_grade"] = "C"
        elif pct >= 70: result["letter_grade"] = "C-"
        elif pct >= 60: result["letter_grade"] = "D"
        else:           result["letter_grade"] = "F"

        return result


# ── Interactive setup ─────────────────────────────────────────────────────────

def _prompt_path(label: str, must_exist: bool = True) -> Path:
    while True:
        raw = input(f"  {label}: ").strip().strip('"')
        p = Path(raw)
        if not must_exist:
            return p
        if p.exists():
            return p
        print(f"    Not found: {p}")


def _interactive_setup() -> dict:
    print("\n=== AI Grading Assistant — Calibrated Pipeline ===\n")
    print("Press Enter after each path. Drag-and-drop the file into the terminal to auto-fill the path.\n")
    instructions = _prompt_path("Assignment instructions (PDF or DOCX)")
    rubric       = _prompt_path("Grading rubric (PDF or DOCX)")
    submissions  = _prompt_path("Student submissions folder")
    output       = _prompt_path("Output folder (will be created if needed)", must_exist=False)
    name         = input("  Assignment name (e.g. 'ISM 6145 Lab 01'): ").strip() or "Assignment"
    return {
        "instructions": str(instructions),
        "rubric":       str(rubric),
        "submissions":  str(submissions),
        "output":       str(output),
        "assignment":   name,
    }


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Calibrated AI grader — works with any assignment")
    parser.add_argument("--instructions",   help="Path to assignment instructions (PDF/DOCX)")
    parser.add_argument("--rubric",         help="Path to grading rubric (PDF/DOCX)")
    parser.add_argument("--submissions",    help="Path to student submissions folder")
    parser.add_argument("--output",         help="Output folder path")
    parser.add_argument("--assignment",     default="Assignment", help="Assignment name for reports")
    parser.add_argument("--offset",         type=float, default=0.0, help="Calibration offset added to raw score (default 0 — bands in prompt control leniency)")
    parser.add_argument("--examples",       help="Path to few-shot examples JSON (see --build-examples)")
    parser.add_argument("--build-examples", action="store_true",
                        help="Build few-shot examples from existing results in --output and save, then exit")
    parser.add_argument("--provider",       default="anthropic", choices=["anthropic", "ollama"],
                        help="Model provider: 'anthropic' (default) or 'ollama' (free, local)")
    parser.add_argument("--model",          default=None,
                        help="Model name. Defaults: anthropic=claude-sonnet-4-6, ollama=qwen2.5:7b")
    parser.add_argument("--ollama-url",     default="http://localhost:11434",
                        help="Ollama server URL (default: http://localhost:11434)")
    parser.add_argument("--rag-mode",       default="keyword", choices=["keyword", "semantic"],
                        help="RAG retrieval mode: 'keyword' (default) or 'semantic' (embedding-based, requires sentence-transformers)")
    parser.add_argument("--criteria",       default=None,
                        help="Path to pre-parsed criteria JSON (skips Claude Haiku rubric parsing — use when API credits are unavailable)")
    parser.add_argument("--pct-full",     type=int, default=SCORING_DEFAULTS["pct_full"],
                        help=f"Lower bound %% for full marks band (default {SCORING_DEFAULTS['pct_full']})")
    parser.add_argument("--pct-good",     type=int, default=SCORING_DEFAULTS["pct_good"],
                        help=f"Lower bound %% for good-attempt band (default {SCORING_DEFAULTS['pct_good']})")
    parser.add_argument("--pct-partial",  type=int, default=SCORING_DEFAULTS["pct_partial"],
                        help=f"Lower bound %% for partial-credit band (default {SCORING_DEFAULTS['pct_partial']})")
    parser.add_argument("--pct-attempt",  type=int, default=SCORING_DEFAULTS["pct_attempt"],
                        help=f"Lower bound %% for minimal-attempt band (default {SCORING_DEFAULTS['pct_attempt']})")
    args = parser.parse_args()

    # ── Build-examples mode: generate examples from existing results ──────────
    if args.build_examples:
        out_dir  = Path(args.output or ".")
        combined = out_dir / "all_results.json"
        if not combined.exists():
            raise FileNotFoundError(f"No all_results.json found in {out_dir}. Run grading first.")
        with open(combined, encoding="utf-8") as f:
            existing = json.load(f)
        examples = build_examples_from_results(existing, n_per_band=1)
        out_path = out_dir / "few_shot_examples.json"
        save_examples(examples, str(out_path))
        print(f"\nFew-shot examples built:")
        print(summarize_examples(examples))
        print(f"\nSaved → {out_path}")
        print(f"Re-run with: python calibrated_grader.py --examples {out_path} ...")
        return

    # Fall back to interactive if args are missing
    if not all([args.instructions, args.rubric, args.submissions, args.output]):
        cfg = _interactive_setup()
        args.instructions = cfg["instructions"]
        args.rubric       = cfg["rubric"]
        args.submissions  = cfg["submissions"]
        args.output       = cfg["output"]
        args.assignment   = cfg["assignment"]

    # ── Provider setup ────────────────────────────────────────────────────────
    provider = args.provider

    if provider == "ollama":
        if not OllamaClient.check_connection(args.ollama_url):
            print(f"\nERROR: Cannot connect to Ollama at {args.ollama_url}")
            print("Fix: open a new Terminal and run:  ollama serve")
            return
        available = OllamaClient.list_models(args.ollama_url)
        model = args.model or "qwen2.5:7b"
        if model not in available:
            print(f"\nERROR: Model '{model}' not found in Ollama.")
            print(f"Available models: {available or '(none)'}")
            print(f"Fix: run  ollama pull {model}")
            return
        print(f"\nUsing local model: {model}  (Ollama — free, runs on your machine)")
        api_key = None
        client  = None
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Missing ANTHROPIC_API_KEY in environment or .env file")
        model  = args.model or "claude-sonnet-4-6"
        client = anthropic.Anthropic(api_key=api_key)
        print(f"\nUsing frontier model: {model}  (Anthropic API)")

    # ── Load documents ────────────────────────────────────────────────────────
    print(f"\nLoading documents...")
    instructions_text = read_document(args.instructions)
    rubric_text       = read_document(args.rubric)
    submissions       = load_student_submissions(args.submissions)
    print(f"  Instructions: {len(instructions_text)} chars")
    print(f"  Rubric:       {len(rubric_text)} chars")
    print(f"  Submissions:  {len(submissions)} student(s)")

    # ── Parse rubric → extract criteria ──────────────────────────────────────────
    if args.criteria:
        print(f"\nLoading pre-parsed criteria from {args.criteria}...")
        with open(args.criteria, encoding="utf-8") as f:
            criteria = json.load(f)
        print(f"  Loaded {len(criteria)} criteria (no API call needed):")
        print(criteria_summary(criteria))
    else:
        print(f"\nParsing rubric...")
        rubric_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not rubric_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY needed for rubric parsing.\n"
                "Tip: if you have pre-parsed criteria, pass --criteria path/to/criteria.json "
                "to skip this step entirely."
            )
        rubric_client = anthropic.Anthropic(api_key=rubric_api_key)
        criteria = parse_rubric_cached(args.rubric, rubric_client)
        print(f"  Found {len(criteria)} criteria:")
        print(criteria_summary(criteria))

    # ── Load few-shot examples (optional) ────────────────────────────────────
    few_shot = []
    if args.examples:
        few_shot = load_examples(args.examples)
        print(f"\nFew-shot examples loaded:")
        print(summarize_examples(few_shot))
    else:
        # Auto-load examples from output dir if they exist
        auto_path = Path(args.output) / "few_shot_examples.json"
        if auto_path.exists():
            few_shot = load_examples(str(auto_path))
            print(f"\nFew-shot examples auto-loaded from {auto_path}:")
            print(summarize_examples(few_shot))

    # ── Grade ─────────────────────────────────────────────────────────────────
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    scoring_bands = {
        "pct_full":    args.pct_full,
        "pct_good":    args.pct_good,
        "pct_partial": args.pct_partial,
        "pct_attempt": args.pct_attempt,
    }
    print(f"\nScoring bands:")
    print(f"  Full marks   : {args.pct_full}–100%")
    print(f"  Good attempt : {args.pct_good}–{args.pct_full - 1}%")
    print(f"  Partial      : {args.pct_partial}–{args.pct_good - 1}%")
    print(f"  Min attempt  : {args.pct_attempt}–{args.pct_partial - 1}%")
    print(f"  Zero         : absent / off-topic")

    grader = CalibratedGrader(
        api_key=api_key,
        criteria=criteria,
        assignment_name=args.assignment,
        model=model,
        calibration_offset=args.offset,
        few_shot_examples=few_shot,
        provider=provider,
        ollama_url=args.ollama_url,
        rag_mode=args.rag_mode,
        scoring_bands=scoring_bands,
    )
    if args.rag_mode == "semantic":
        print(f"\nRAG mode: semantic (sentence-transformer embeddings)")
    else:
        print(f"\nRAG mode: keyword (default)")

    print(f"\nGrading {len(submissions)} student(s) with {grader.model}...\n")

    all_results = []
    student_ids = []

    for idx, submission in enumerate(submissions, start=1):
        student_id = f"Student_{idx:03d}"
        student_ids.append(student_id)
        print(f"  [{idx:02d}/{len(submissions)}] {student_id}  ({submission['name']})...", end=" ", flush=True)

        result = grader.grade_submission(
            instructions_text=instructions_text,
            submission_text=submission["text"],
            student_id=student_id,
            student_name=submission["name"],
        )

        out_file = output_dir / f"{student_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        raw = result.get("total_score_raw", result.get("total_score", "?"))
        cal = result.get("total_score", "?")
        max_s = result.get("max_score", "?")
        print(f"raw={raw}/{max_s}  calibrated={cal}/{max_s}  ({result.get('letter_grade','?')})")

        all_results.append(result)
        if idx < len(submissions):
            time.sleep(0.5)

    # ── Save outputs ──────────────────────────────────────────────────────────
    combined = output_dir / "all_results.json"
    with open(combined, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    template_csv = output_dir / "gold_standard_template.csv"
    criterion_names = [c["name"] for c in criteria]
    create_gold_standard_template(str(template_csv), student_ids, criterion_names)

    print(f"\n{'='*55}")
    print(f"  DONE — {len(all_results)} students graded")
    print(f"  Results      → {combined}")
    print(f"  Gold std CSV → {template_csv}")
    print(f"\n  Next steps:")
    print(f"  1. Fill in human scores in: {template_csv.name}")
    print(f"  2. Run dashboard: python dashboard.py --input {combined}")
    print(f"  3. Run eval:      python evaluator.py --human {template_csv} --ai {combined}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
