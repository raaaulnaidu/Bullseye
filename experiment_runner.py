"""
experiment_runner.py
--------------------
Design of Experiments — 4 grading configurations on the same submissions.

Set 1 — Baseline       : Full raw submission + generic TA prompt
Set 2 — Rubric-Calibrated : Full submission + calibrated rubric rules
Set 3 — Privacy + RAG  : Anonymized + RAG evidence chunks only
Set 4 — Few-Shot + RAG : Anonymized + RAG + human-graded examples in prompt

Usage:
    python experiment_runner.py
    python experiment_runner.py --sets 1 2 3 4
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
from typing import Dict, List

import anthropic

from document_reader import read_document, load_student_submissions
from privacy_processor import anonymize
from rag_retriever import build_rag_evidence, LAB01_CRITERIA
from evaluator import load_human_grades, load_ai_grades, compute_metrics, generate_report


# ── Few-shot examples (from human TA grades in XLSX) ─────────────────────────
# Three anchors: high / mid / lower scorer

FEW_SHOT_EXAMPLES = """
─────────────────────────────────────────────────────────────────
CALIBRATION EXAMPLES — How the human TA grades this rubric
─────────────────────────────────────────────────────────────────

EXAMPLE A — Strong submission (20/20)
  Context (4/4):
    "Picked up the context correctly — role, goal, audience and
     constraints all clearly stated."
  Understand table (5/5):
    "Understood the table and explained well, with all the
     attributes (Sentiment, Theme, Priority, Evidence) correctly
     filled for all 10 reviews."
  Evidence checks (6/6):
    "Clear evidence checks. Correctly calculated the revenue
     decline and identified the right 2 drivers from Data A and
     Data B."
  Memo quality (4/4):
    "The memo is professional and well structured — covers
     Situation, Data insights, Recommendation, and Owner/next
     step within the word limit."
  AI Use Note (1/1):
    "Good approach — prompts are documented, meaningful changes
     listed, and at least one limitation identified."

EXAMPLE B — Mid-range submission (17/20)
  Context (4/4):
    "Student gave a feasible context — all four fields present."
  Understand table (5/5):
    "Well explained and understood table with all the
     factors/parameters."
  Evidence checks (4/6):
    "Inaccurate calculations: the revenue decline figure (0.83)
     is incorrect. Partial credit for attempting the calculation
     and identifying some drivers."
  Memo quality (3/4):
    "Memo exceeds the word limit and lacks clear structure.
     Situation and recommendation are present but the memo reads
     more like an essay than a professional brief."
  AI Use Note (1/1):
    "Decent AI approach — prompts described."

EXAMPLE C — Weaker submission (13/20)
  Context (2/4):
    "Very generic and incomplete. Missing explicit role,
     audience, constraints, and goal structure required by the
     template. Half marks awarded for partial attempt."
  Understand table (3/5):
    "Did not use the actual Bayside Brew review snippets from
     the assignment. Multiple reviews were invented or changed
     completely. Partial credit for table structure."
  Evidence checks (3/6):
    "Completely incorrect evidence section. Used fabricated
     sales numbers ($48,000 → $54,000) instead of the provided
     Week 1–8 revenue data. Did not calculate the required
     Bayside Brew revenue change. Partial credit for attempting
     a structured evidence section."
  Memo quality (4/4):
    "Memo is actually reasonably written and professional,
     though it is based partly on incorrect/fabricated evidence."
  AI Use Note (1/1):
    "Completed appropriately."

─────────────────────────────────────────────────────────────────
Use these examples to CALIBRATE your scoring. Match the
strictness level shown — do not inflate or deflate grades
beyond this scale.
─────────────────────────────────────────────────────────────────
"""


# ── System prompts per set ────────────────────────────────────────────────────

SYSTEM_SET1 = """You are a Teaching Assistant grading a student assignment.
Grade fairly and return ONLY a valid JSON object.

JSON FORMAT:
{
  "student_id": "",
  "total_score": 0,
  "max_score": 20,
  "percentage": 0.0,
  "criteria": [
    {"name": "", "max_points": 0, "awarded_points": 0,
     "completed": "", "missing_or_weak": "", "suggestion": ""}
  ],
  "overall_feedback": "",
  "consistency_notes": ""
}"""

SYSTEM_SET2 = """You are an expert Teaching Assistant for CAI 3801.

IMPORTANT RULES:
- Be lenient and constructive. Focus on whether required sections are present.
- Award partial credit for reasonable attempts.
- Do NOT harshly penalize wording or writing style.
- Use the SAME grading interpretation for all students.
- Do not invent missing work.

Rubric:
1. Context          = 4 pts  (Role, Goal, Audience, Constraints)
2. Understand table = 5 pts  (10-row review labeling table)
3. Evidence checks  = 6 pts  (Revenue calc + Data A/B drivers + linked bullets)
4. Memo quality     = 4 pts  (Situation, Insights, Recommendation, Owner/timeline)
5. AI Use Note      = 1 pt   (Prompts used, changes made, limitations)

For EACH criterion state: what was completed, what is missing/weak, one suggestion.
Return ONLY valid JSON — no markdown fences.

JSON FORMAT:
{
  "student_id": "",
  "total_score": 0,
  "max_score": 20,
  "percentage": 0.0,
  "criteria": [
    {"name": "", "max_points": 0, "awarded_points": 0,
     "completed": "", "missing_or_weak": "", "suggestion": ""}
  ],
  "overall_feedback": "",
  "consistency_notes": ""
}"""

SYSTEM_SET3 = SYSTEM_SET2  # Same prompt, different input (RAG + anonymized)

SYSTEM_SET4 = SYSTEM_SET2 + "\n\n" + FEW_SHOT_EXAMPLES


# ── User prompt templates ─────────────────────────────────────────────────────

USER_FULL = """
ASSIGNMENT GUIDE:
{guide}

STUDENT TEMPLATE:
{template}

STUDENT SUBMISSION:
{submission}

Evaluate and return ONLY JSON.
"""

USER_RAG = """
ASSIGNMENT GUIDE:
{guide}

STUDENT TEMPLATE:
{template}

RUBRIC-EXTRACTED EVIDENCE (anonymized, most relevant portions only):
{rag_evidence}

Evaluate ONLY the evidence shown. If a criterion has no evidence, award 0.
Return ONLY JSON.
"""


# ── Grader ────────────────────────────────────────────────────────────────────

class ExperimentGrader:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def grade(self, system: str, user_prompt: str, student_id: str) -> Dict:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2500,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m: cleaned = m.group()
        result = json.loads(cleaned)
        result["student_id"] = student_id
        return result

    def run_set(
        self,
        set_num: int,
        submissions: List[Dict],
        guide_text: str,
        template_text: str,
        output_dir: Path,
    ) -> List[Dict]:
        system_map = {1: SYSTEM_SET1, 2: SYSTEM_SET2, 3: SYSTEM_SET3, 4: SYSTEM_SET4}
        system = system_map[set_num]
        results = []

        print(f"\n── Set {set_num} ─────────────────────────────────")
        for idx, sub in enumerate(submissions, 1):
            sid = f"Student_{idx:03d}"
            print(f"  Grading {sid} ({sub['name']})...", end=" ", flush=True)

            if set_num in (3, 4):
                # Anonymize + RAG
                anon_text, _ = anonymize(sub["text"], known_name=sub["name"])
                rag = build_rag_evidence(anon_text, criteria=LAB01_CRITERIA, top_n=3)
                prompt = USER_RAG.format(guide=guide_text, template=template_text, rag_evidence=rag)
            else:
                # Full raw submission
                prompt = USER_FULL.format(guide=guide_text, template=template_text, submission=sub["text"])

            try:
                result = self.grade(system, prompt, sid)
                print(f"{result.get('total_score', '?')}/20")
            except Exception as e:
                print(f"ERROR: {e}")
                result = {"student_id": sid, "total_score": 0, "max_score": 20,
                          "percentage": 0.0, "criteria": [], "overall_feedback": str(e),
                          "consistency_notes": "", "error": str(e)}

            results.append(result)
            if idx < len(submissions):
                time.sleep(0.5)

        # Save set results
        out_file = output_dir / f"set{set_num}_results.json"
        with open(out_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  Saved → {out_file}")
        return results


# ── Comparison report ─────────────────────────────────────────────────────────

def compare_sets(all_set_results: Dict[int, List[Dict]], output_dir: Path):
    """Generate a side-by-side comparison of all 4 sets."""
    report_lines = []
    L = report_lines.append

    L("=" * 70)
    L("  DESIGN OF EXPERIMENTS — GRADING COMPARISON REPORT")
    L(f"  Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    L("=" * 70)

    set_labels = {
        1: "Set 1 — Baseline (full raw submission, generic prompt)",
        2: "Set 2 — Rubric-Calibrated (full submission, calibrated prompt)",
        3: "Set 3 — Privacy + RAG (anonymized + evidence chunks)",
        4: "Set 4 — Few-Shot + RAG (anonymized + RAG + human examples)",
    }

    # Per-student scores across sets
    n_students = len(next(iter(all_set_results.values())))
    L(f"\n── PER-STUDENT SCORE COMPARISON (out of 20) {'─'*20}")
    header = f"  {'Student':<14}" + "".join(f"  {'S'+str(s):>6}" for s in sorted(all_set_results))
    L(header)
    L("  " + "─" * (len(header) - 2))

    for i in range(n_students):
        sid = f"Student_{i+1:03d}"
        row = f"  {sid:<14}"
        for s in sorted(all_set_results):
            results = all_set_results[s]
            if i < len(results):
                row += f"  {results[i].get('total_score', '?'):>6}"
        L(row)

    # Set-level averages
    L(f"\n── SET AVERAGES {'─'*50}")
    for s in sorted(all_set_results):
        results = all_set_results[s]
        scores = [r.get("total_score", 0) for r in results]
        avg = sum(scores) / len(scores) if scores else 0
        mn, mx = min(scores), max(scores)
        L(f"\n  {set_labels[s]}")
        L(f"    Avg: {avg:.2f}/20  |  Min: {mn}  |  Max: {mx}  |  Students: {len(scores)}")

    # Per-criterion averages per set
    L(f"\n── CRITERION AVERAGES PER SET {'─'*38}")
    criteria = ["Context", "Understand table", "Evidence checks", "Memo quality", "AI Use Note"]
    L(f"  {'Criterion':<22}" + "".join(f"  {'S'+str(s):>6}" for s in sorted(all_set_results)))
    L("  " + "─" * 60)
    for c in criteria:
        row = f"  {c:<22}"
        for s in sorted(all_set_results):
            results = all_set_results[s]
            vals = [cr.get("awarded_points", 0)
                    for r in results
                    for cr in r.get("criteria", [])
                    if cr.get("name") == c]
            avg = sum(vals) / len(vals) if vals else 0
            row += f"  {avg:>6.2f}"
        L(row)

    # If gold standard available, show vs human
    gold_path = output_dir.parent / "gold_standard_template.csv"
    if gold_path.exists():
        L(f"\n── VS HUMAN TA GOLD STANDARD {'─'*40}")
        human = load_human_grades(str(gold_path))
        L(f"  {'Set':<8}  {'MAE':>6}  {'Within±1pt':>11}  {'Bias':>7}  {'Corr r':>8}")
        L("  " + "─" * 50)
        for s in sorted(all_set_results):
            ai_path = output_dir / f"set{s}_results.json"
            if not ai_path.exists(): continue
            ai = load_ai_grades(str(ai_path))
            try:
                m = compute_metrics(human, ai)
                ov = m["overall"]
                L(f"  Set {s:<4}  {ov['mae']:>6.3f}  {ov['within_1pt_pct']:>10.1f}%"
                  f"  {ov['bias']:>+7.3f}  {ov['correlation']:>8.3f}")
            except ValueError:
                L(f"  Set {s:<4}  (no common students with gold standard)")

    L("\n" + "=" * 70)

    report_path = output_dir / "experiment_comparison.txt"
    with open(report_path, "w") as f:
        f.write("\n".join(report_lines))
    print(f"\nComparison report → {report_path}")
    print("\n".join(report_lines))
    return report_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run grading experiment sets")
    parser.add_argument("--sets", nargs="+", type=int, default=[1, 2, 3, 4],
                        help="Which sets to run (default: all 4)")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Missing ANTHROPIC_API_KEY")

    source_dir = Path("lab01_data/source_files")
    guide_text    = read_document(str(source_dir / "CAI3801_Lab01_StepByStep_Guide.pdf"))
    template_text = read_document(str(source_dir / "CAI3801_Lab01_Student_Template.docx"))
    submissions   = load_student_submissions("lab01_data/student_submissions")

    print(f"Submissions loaded: {len(submissions)}")
    print(f"Running sets: {args.sets}\n")

    output_dir = Path("lab01_data/experiments")
    output_dir.mkdir(parents=True, exist_ok=True)

    grader = ExperimentGrader(api_key)
    all_results = {}

    for set_num in args.sets:
        results = grader.run_set(set_num, submissions, guide_text, template_text, output_dir)
        all_results[set_num] = results

    # Load any previously run sets not in this run
    for s in [1, 2, 3, 4]:
        if s not in all_results:
            p = output_dir / f"set{s}_results.json"
            if p.exists():
                with open(p) as f:
                    all_results[s] = json.load(f)

    compare_sets(all_results, output_dir)


if __name__ == "__main__":
    main()
