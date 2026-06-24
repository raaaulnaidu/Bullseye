"""
batch_grader.py
---------------
Grades an entire class using the Anthropic Batch API.
Sends all students in one request — 50% cheaper than individual calls,
ideal for 30–500 students.

Workflow:
  1. Submit batch  → get a batch_id (takes ~10 seconds)
  2. Wait          → Anthropic processes in background (up to 24 hours, usually 1–2 hours)
  3. Check + save  → download results and generate dashboard + CSV

Usage:
  # Step 1 — Submit all 100 students
  python batch_grader.py submit \\
      --instructions "lab01_data/source_files/CAI3801_Lab01_StepByStep_Guide.pdf" \\
      --rubric       "lab01_data/source_files/CAI3801_Lab01_Rubric.pdf" \\
      --submissions  "lab01_data/student_submissions/" \\
      --output       "lab01_data/output_batch/" \\
      --assignment   "CAI 3801 — Lab 01 Summer 2026"

  # Step 2 — Check status (run any time after submitting)
  python batch_grader.py check --output "lab01_data/output_batch/"

  # Step 3 — When status shows 'ended', results are already saved automatically
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
from datetime import datetime
from typing import List, Dict

import anthropic

from document_reader import read_document, load_student_submissions
from privacy_processor import anonymize
from rag_retriever import build_rag_evidence
from rubric_parser import parse_rubric, criteria_summary, build_rubric_prompt_section
from few_shot_builder import load_examples, format_as_turns, summarize_examples
from calibrated_grader import _SYSTEM_TEMPLATE, _USER_TEMPLATE, CalibratedGrader
from evaluator import create_gold_standard_template
from dashboard import build_dashboard


# ── Batch submission ───────────────────────────────────────────────────────────

def build_requests(
    submissions: List[Dict],
    instructions_text: str,
    criteria: List[Dict],
    assignment_name: str,
    few_shot_examples: List[Dict] = None,
    calibration_offset: float = 3.5,
) -> List[Dict]:
    """
    Build a list of Batch API request objects — one per student.
    Each request is fully self-contained: anonymized, RAG-extracted, prompted.
    """
    max_score = sum(c["max_points"] for c in criteria)
    system_prompt = _SYSTEM_TEMPLATE.format(
        assignment_name=assignment_name,
        rubric_section=build_rubric_prompt_section(criteria),
        max_score=max_score,
    )

    requests = []
    for idx, submission in enumerate(submissions, start=1):
        student_id = f"Student_{idx:03d}"

        # Anonymize locally
        anon_text, _ = anonymize(submission["text"], known_name=submission["name"])

        # RAG evidence
        rag_evidence = build_rag_evidence(anon_text, criteria=criteria, top_n=3)

        # Build messages (few-shot turns + real student)
        student_prompt = _USER_TEMPLATE.format(
            instructions=instructions_text[:3000],
            rag_evidence=rag_evidence,
        )
        messages = []
        if few_shot_examples:
            messages += format_as_turns(few_shot_examples, _USER_TEMPLATE, instructions_text)
        messages.append({"role": "user", "content": student_prompt})

        requests.append({
            "custom_id": student_id,
            "params": {
                "model":      "claude-sonnet-4-6",
                "max_tokens": 2500,
                "system":     system_prompt,
                "messages":   messages,
            }
        })

    return requests


def submit_batch(
    requests: List[Dict],
    client: anthropic.Anthropic,
    output_dir: Path,
    metadata: Dict,
) -> str:
    """Submit requests to the Batch API. Returns the batch_id."""
    print(f"\nSubmitting {len(requests)} requests to Batch API...")

    batch = client.messages.batches.create(requests=requests)
    batch_id = batch.id

    # Save batch metadata so we can check status later
    meta_path = output_dir / "batch_meta.json"
    metadata["batch_id"]   = batch_id
    metadata["submitted"]  = datetime.now().isoformat()
    metadata["n_students"] = len(requests)
    metadata["status"]     = "submitted"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n{'='*55}")
    print(f"  Batch submitted successfully!")
    print(f"  Batch ID : {batch_id}")
    print(f"  Students : {len(requests)}")
    print(f"  Est. cost: ${len(requests) * 0.028:.2f}  (50% batch discount)")
    print(f"  Est. time: 1–24 hours")
    print(f"\n  Check status anytime:")
    print(f"  python batch_grader.py check --output \"{output_dir}\"")
    print(f"{'='*55}\n")

    return batch_id


# ── Status check + result download ────────────────────────────────────────────

def check_batch(output_dir: Path, client: anthropic.Anthropic, criteria: List[Dict] = None, calibration_offset: float = 3.5):
    """Check batch status. If complete, download and save results."""
    meta_path = output_dir / "batch_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"No batch_meta.json found in {output_dir}. Run 'submit' first.")

    with open(meta_path) as f:
        meta = json.load(f)

    batch_id       = meta["batch_id"]
    assignment     = meta.get("assignment_name", "Assignment")
    n_students     = meta.get("n_students", 0)
    submitted_at   = meta.get("submitted", "")

    print(f"\nChecking batch: {batch_id}")
    print(f"Assignment    : {assignment}")
    print(f"Students      : {n_students}")
    print(f"Submitted     : {submitted_at}")

    batch = client.messages.batches.retrieve(batch_id)
    status = batch.processing_status

    counts = batch.request_counts
    print(f"\nStatus        : {status.upper()}")
    print(f"  Processing  : {counts.processing}")
    print(f"  Succeeded   : {counts.succeeded}")
    print(f"  Errored     : {counts.errored}")
    print(f"  Expired     : {counts.expired}")

    if status != "ended":
        print(f"\nNot ready yet — check again later.")
        return

    # Download and process results
    print(f"\nBatch complete! Downloading results...")
    _save_results(batch_id, output_dir, client, meta, calibration_offset)


def _save_results(
    batch_id: str,
    output_dir: Path,
    client: anthropic.Anthropic,
    meta: Dict,
    calibration_offset: float,
):
    """Download batch results, apply calibration, save all outputs."""
    criteria        = meta.get("criteria", [])
    assignment_name = meta.get("assignment_name", "Assignment")
    max_score       = sum(c["max_points"] for c in criteria) if criteria else 20

    all_results = []
    errors = []

    for result in client.messages.batches.results(batch_id):
        sid = result.custom_id

        if result.result.type != "succeeded":
            errors.append({"student_id": sid, "error": str(result.result)})
            print(f"  ERROR — {sid}: {result.result.type}")
            continue

        raw_text = result.result.message.content[0].text.strip()

        # Parse JSON
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group()

        try:
            r = json.loads(cleaned)
        except json.JSONDecodeError:
            errors.append({"student_id": sid, "error": "JSON parse failed", "raw": raw_text[:200]})
            print(f"  PARSE ERROR — {sid}")
            continue

        r["student_id"]      = sid
        r["max_score"]       = max_score
        r["assignment_name"] = assignment_name
        r["rubric_criteria"] = criteria

        # Apply calibration
        if calibration_offset != 0 and criteria:
            dummy = CalibratedGrader.__new__(CalibratedGrader)
            dummy.calibration_offset = calibration_offset
            dummy.max_score = max_score
            r = dummy._apply_calibration(r)

        # Save individual file
        with open(output_dir / f"{sid}.json", "w") as f:
            json.dump(r, f, indent=2)

        total = r.get("total_score", "?")
        grade = r.get("letter_grade", "?")
        print(f"  {sid}  {total}/{max_score}  ({grade})")
        all_results.append(r)

    # Sort by student_id
    all_results.sort(key=lambda r: r.get("student_id", ""))

    # Save combined results
    combined = output_dir / "all_results.json"
    with open(combined, "w") as f:
        json.dump(all_results, f, indent=2)

    # Save error log if any
    if errors:
        with open(output_dir / "errors.json", "w") as f:
            json.dump(errors, f, indent=2)
        print(f"\n  {len(errors)} error(s) saved to errors.json")

    # Generate dashboard
    dash_path = output_dir / "dashboard.html"
    html = build_dashboard(all_results, assignment_name=assignment_name)
    with open(dash_path, "w") as f:
        f.write(html)

    # Generate gold standard template
    student_ids = [r["student_id"] for r in all_results]
    crit_names  = [c["name"] for c in criteria] if criteria else []
    create_gold_standard_template(
        str(output_dir / "gold_standard_template.csv"),
        student_ids,
        crit_names,
    )

    print(f"\n{'='*55}")
    print(f"  DONE — {len(all_results)} students saved")
    print(f"  Results   → {combined}")
    print(f"  Dashboard → {dash_path}")
    print(f"\n  Open dashboard: file://{dash_path.resolve()}")
    print(f"{'='*55}\n")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Batch grader — 50% cheaper for large classes")
    sub = parser.add_subparsers(dest="command", required=True)

    # submit
    s = sub.add_parser("submit", help="Submit all students to the Batch API")
    s.add_argument("--instructions", required=True)
    s.add_argument("--rubric",       required=True)
    s.add_argument("--submissions",  required=True)
    s.add_argument("--output",       required=True)
    s.add_argument("--assignment",   default="Assignment")
    s.add_argument("--examples",     help="Path to few-shot examples JSON (optional)")
    s.add_argument("--offset",       type=float, default=3.5)

    # check
    c = sub.add_parser("check", help="Check batch status and download results when ready")
    c.add_argument("--output", required=True)
    c.add_argument("--offset", type=float, default=3.5)

    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Missing ANTHROPIC_API_KEY in .env file")
    client = anthropic.Anthropic(api_key=api_key)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "submit":
        print("\nLoading documents...")
        instructions_text = read_document(args.instructions)
        rubric_text       = read_document(args.rubric)
        submissions       = load_student_submissions(args.submissions)
        print(f"  Instructions : {len(instructions_text)} chars")
        print(f"  Rubric       : {len(rubric_text)} chars")
        print(f"  Submissions  : {len(submissions)} student(s)")

        print("\nParsing rubric with Claude Haiku...")
        criteria = parse_rubric(rubric_text, client)
        print(f"  Found {len(criteria)} criteria:")
        print(criteria_summary(criteria))

        # Load few-shot examples
        few_shot = []
        examples_path = args.examples or str(output_dir / "few_shot_examples.json")
        if Path(examples_path).exists():
            few_shot = load_examples(examples_path)
            print(f"\nFew-shot examples loaded:")
            print(summarize_examples(few_shot))

        print(f"\nBuilding {len(submissions)} prompts (anonymize + RAG)...")
        requests = build_requests(
            submissions=submissions,
            instructions_text=instructions_text,
            criteria=criteria,
            assignment_name=args.assignment,
            few_shot_examples=few_shot,
            calibration_offset=args.offset,
        )

        meta = {
            "assignment_name": args.assignment,
            "criteria":        criteria,
            "calibration_offset": args.offset,
            "instructions":    args.instructions,
            "rubric":          args.rubric,
            "submissions":     args.submissions,
        }
        submit_batch(requests, client, output_dir, meta)

    elif args.command == "check":
        meta_path = output_dir / "batch_meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        criteria = meta.get("criteria", [])
        check_batch(output_dir, client, criteria=criteria, calibration_offset=args.offset)


if __name__ == "__main__":
    main()
