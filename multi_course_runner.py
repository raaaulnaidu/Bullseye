#!/usr/bin/env python3
"""
multi_course_runner.py
----------------------
Grades both courses in one command and routes students to TAs automatically.

Courses:
  Course 1 — AI for Analytics         (TA1 + TA2)
  Course 2 — Foundation of Business Statistics  (TA3 + TA4)

What it produces for each course:
  • all_results.json           — structured grades
  • dashboard.html             — per-course visual dashboard
  • gold_standard_template.csv — fill with human scores for evaluation
  • ta_assignments/            — per-TA student subsets (JSON + HTML)

Plus a combined TA overview HTML at: output/combined_overview.html

Usage (interactive):
    python multi_course_runner.py

Usage (command-line, both courses):
    python multi_course_runner.py \\
        --course1-instructions  path/to/ai_analytics_instructions.pdf \\
        --course1-rubric        path/to/ai_analytics_rubric.pdf \\
        --course1-submissions   path/to/ai_analytics_submissions/ \\
        --course2-instructions  path/to/stats_instructions.pdf \\
        --course2-rubric        path/to/stats_rubric.pdf \\
        --course2-submissions   path/to/stats_submissions/ \\
        --output                path/to/output_folder/ \\
        --offset                3.5

Usage (single course only):
    python multi_course_runner.py \\
        --course1-instructions  path/to/instructions.pdf \\
        --course1-rubric        path/to/rubric.pdf \\
        --course1-submissions   path/to/submissions/ \\
        --output                path/to/output_folder/
"""

from pathlib import Path
import os

# Load .env file
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
import time
import re
from datetime import datetime
from typing import List, Dict, Optional

import anthropic

from document_reader import read_document, load_student_submissions
from privacy_processor import anonymize
from rag_retriever import build_rag_evidence
from rubric_parser import parse_rubric, criteria_summary, build_rubric_prompt_section
from evaluator import create_gold_standard_template
from dashboard import build_dashboard


# ─── TA Configuration ──────────────────────────────────────────────────────────
# Adjust names and split sizes to match your actual TAs.
# Students are assigned sequentially — first N go to TA1, next N to TA2, etc.

COURSE_CONFIG = {
    "AI for Analytics": {
        "code":    "CAI_3801",
        "tas":     ["TA1", "TA2"],
        "split":   "equal",   # "equal" | integer (e.g. 100 = first 100 go to TA1)
    },
    "Foundation of Business Statistics": {
        "code":    "ISM_6145",
        "tas":     ["TA3", "TA4"],
        "split":   "equal",
    },
}

# ─── Grading prompt templates (same as calibrated_grader.py) ──────────────────

_SYSTEM_TEMPLATE = """
You are an expert Teaching Assistant grading student submissions.

Your goal is to provide CONSISTENT rubric-calibrated grading that matches
how a fair human TA would grade — not stricter.

CALIBRATION GUIDANCE (based on observed human TA grading patterns):
- A student who attempts all sections and shows reasonable effort typically earns 80–95% of total points.
- Only award 0 for a criterion when that section is entirely absent from the submission.
- Award 50–75% of points when the student made a clear attempt but had gaps.
- Award 80–100% of points when the work is present and mostly correct.
- Do NOT deduct points for minor wording differences, informal phrasing, or imperfect formatting.

IMPORTANT RULES:
- Be lenient and constructive — match the generosity of a supportive human TA.
- Focus mainly on whether required sections are present and the student attempted the task.
- Award partial credit generously for reasonable attempts.
- Do NOT harshly penalize wording or writing style.
- Use the SAME grading interpretation for all students.
- Do not invent missing work.
- Grade ONLY the evidence provided — do not assume content not shown.

Assignment: {assignment_name}
Course: {course_name}

Rubric:
{rubric_section}

For EACH criterion:
1. State what was completed (based on the provided evidence)
2. State what is missing or weak
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


# ─── Core grader (mirrors CalibratedGrader from calibrated_grader.py) ─────────

def _apply_calibration(result: dict, criteria: List[Dict], calibration_offset: float) -> dict:
    """Apply calibration offset proportionally across criteria."""
    max_score = result.get("max_score", sum(c["max_points"] for c in criteria))
    crit_list = result.get("criteria", [])
    crit_total = sum(c.get("max_points", 0) for c in crit_list)

    for c in crit_list:
        cmax = c.get("max_points", 0)
        prop = calibration_offset * (cmax / crit_total) if crit_total > 0 else 0
        raw = c.get("awarded_points", 0)
        c["awarded_points"] = round(min(cmax, raw + prop), 1)
        c["awarded_points_raw"] = raw

    raw_total = result.get("total_score", 0)
    calibrated = round(min(max_score, raw_total + calibration_offset), 1)
    result["total_score"] = calibrated
    result["total_score_raw"] = raw_total
    result["calibration_offset_applied"] = calibration_offset
    result["percentage"] = round((calibrated / max_score) * 100, 1) if max_score else 0

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


def grade_submission(
    client: anthropic.Anthropic,
    model: str,
    criteria: List[Dict],
    assignment_name: str,
    course_name: str,
    instructions_text: str,
    submission: Dict,
    student_id: str,
    calibration_offset: float,
) -> Dict:
    """Grade a single submission: anonymize → RAG → Claude → calibrate."""
    anon_text, anon_log = anonymize(submission["text"], known_name=submission["name"])
    if anon_log:
        print(f"      [privacy] {student_id}: {', '.join(anon_log)}")

    rag_evidence = build_rag_evidence(anon_text, criteria=criteria, top_n=3)
    max_score = sum(c["max_points"] for c in criteria)

    system = _SYSTEM_TEMPLATE.format(
        assignment_name=assignment_name,
        course_name=course_name,
        rubric_section=build_rubric_prompt_section(criteria),
        max_score=max_score,
    )
    user = _USER_TEMPLATE.format(
        instructions=instructions_text[:3000],
        rag_evidence=rag_evidence,
    )

    response = client.messages.create(
        model=model,
        max_tokens=2500,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    raw_text = response.content[0].text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        cleaned = m.group()

    result = json.loads(cleaned)
    result["student_id"] = student_id
    result["student_name"] = submission["name"]
    result["source_file"] = submission.get("file", "")
    result["assignment_name"] = assignment_name
    result["course_name"] = course_name
    result["rubric_criteria"] = criteria

    return _apply_calibration(result, criteria, calibration_offset)


# ─── TA assignment routing ────────────────────────────────────────────────────

def assign_tas(results: List[Dict], tas: List[str], split) -> Dict[str, List[Dict]]:
    """
    Assign graded results to TAs.

    split = "equal"  → split evenly
    split = int N    → first N to TA1, rest to TA2 (for 2 TAs)
    """
    n = len(results)
    assignments: Dict[str, List[Dict]] = {ta: [] for ta in tas}

    if split == "equal":
        chunk = max(1, -(-n // len(tas)))   # ceiling division
        for i, r in enumerate(results):
            ta = tas[min(i // chunk, len(tas) - 1)]
            assignments[ta].append(r)
    elif isinstance(split, int):
        for i, r in enumerate(results):
            ta = tas[0] if i < split else tas[1]
            assignments[ta].append(r)

    return assignments


# ─── Per-TA HTML mini-dashboard ───────────────────────────────────────────────

def build_ta_html(ta_name: str, course_name: str, results: List[Dict]) -> str:
    """Build a simple HTML page listing this TA's assigned students."""
    rows = ""
    for r in results:
        pct = r.get("percentage", 0)
        color = "#22c55e" if pct >= 80 else "#3b82f6" if pct >= 60 else "#ef4444"
        rows += f"""
        <tr>
          <td>{r.get("student_id","")}</td>
          <td>{r.get("student_name","")}</td>
          <td style="color:{color};font-weight:700">{r.get("total_score","?")}/{r.get("max_score","?")}</td>
          <td style="color:{color};font-weight:700">{pct}%</td>
          <td style="color:{color};font-weight:700">{r.get("letter_grade","?")}</td>
          <td style="color:#64748b;font-size:.8rem">{r.get("overall_feedback","")[:120]}…</td>
        </tr>"""

    scores = [r.get("percentage", 0) for r in results]
    avg = round(sum(scores) / len(scores), 1) if scores else 0
    pending = len(results)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{ta_name} — {course_name}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,sans-serif;background:#f1f5f9;color:#1e293b;padding:28px 20px}}
.container{{max-width:1000px;margin:0 auto}}
.hdr{{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;border-radius:14px;padding:26px 30px;margin-bottom:22px}}
.hdr h1{{font-size:1.4rem;margin-bottom:4px}}
.hdr p{{opacity:.8;font-size:.85rem}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:22px}}
.stat{{background:#fff;border-radius:10px;padding:18px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.stat-val{{font-size:1.9rem;font-weight:700;color:#4f46e5}}
.stat-lbl{{font-size:.75rem;color:#64748b;text-transform:uppercase;margin-top:2px}}
.card{{background:#fff;border-radius:12px;padding:22px;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.card h2{{font-size:.85rem;text-transform:uppercase;color:#64748b;letter-spacing:.06em;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;font-size:.85rem}}
th{{background:#f8fafc;padding:9px 12px;text-align:left;color:#4f46e5;font-size:.78rem;text-transform:uppercase;border-bottom:2px solid #e2e8f0}}
td{{padding:10px 12px;border-bottom:1px solid #f1f5f9;vertical-align:top}}
tr:last-child td{{border:none}}
.note{{background:#eff6ff;border-left:4px solid #3b82f6;border-radius:0 8px 8px 0;padding:10px 14px;font-size:.82rem;color:#1e40af;margin-top:16px}}
</style>
</head>
<body>
<div class="container">
  <div class="hdr">
    <h1>📋 {ta_name} — Review Queue</h1>
    <p>{course_name} · Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-val">{len(results)}</div><div class="stat-lbl">Students Assigned</div></div>
    <div class="stat"><div class="stat-val">{avg}%</div><div class="stat-lbl">Avg Score</div></div>
    <div class="stat"><div class="stat-val">{pending}</div><div class="stat-lbl">Pending Review</div></div>
  </div>
  <div class="card">
    <h2>Students — Review AI Grades Below</h2>
    <table>
      <thead><tr><th>ID</th><th>Student</th><th>Score</th><th>%</th><th>Grade</th><th>AI Feedback Preview</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <div class="note">⚠️ These are AI-generated grades. Please review each student and override any grades you disagree with before finalizing.</div>
  </div>
</div>
</body>
</html>"""


# ─── Combined overview dashboard ──────────────────────────────────────────────

def build_combined_overview(course_summaries: List[Dict]) -> str:
    """Build a single HTML page summarizing both courses for the lead TA / professor."""
    course_cards = ""
    for cs in course_summaries:
        results = cs["results"]
        scores = [r.get("percentage", 0) for r in results]
        avg = round(sum(scores) / len(scores), 1) if scores else 0
        passing = sum(1 for s in scores if s >= 60)
        dist = {"A": 0, "B": 0, "C": 0, "D/F": 0}
        for s in scores:
            if s >= 90:   dist["A"] += 1
            elif s >= 80: dist["B"] += 1
            elif s >= 70: dist["C"] += 1
            else:         dist["D/F"] += 1

        ta_rows = ""
        for ta, ta_results in cs["ta_assignments"].items():
            ta_scores = [r.get("percentage", 0) for r in ta_results]
            ta_avg = round(sum(ta_scores) / len(ta_scores), 1) if ta_scores else 0
            ta_rows += f"<tr><td>{ta}</td><td>{len(ta_results)} students</td><td>{ta_avg}%</td></tr>"

        color = "#22c55e" if avg >= 80 else "#3b82f6" if avg >= 60 else "#ef4444"
        course_cards += f"""
        <div class="course-card">
          <div class="course-hdr">
            <div>
              <div class="course-title">{cs['course_name']}</div>
              <div class="course-code">{cs['assignment_name']}</div>
            </div>
            <div class="course-avg" style="color:{color}">{avg}%</div>
          </div>
          <div class="course-stats">
            <div class="cs"><div class="csv">{len(results)}</div><div class="csl">Students</div></div>
            <div class="cs"><div class="csv">{passing}</div><div class="csl">Passing</div></div>
            <div class="cs"><div class="csv">{dist['A']}</div><div class="csl">A grades</div></div>
            <div class="cs"><div class="csv">{dist['B']}</div><div class="csl">B grades</div></div>
            <div class="cs"><div class="csv">{dist['C']}</div><div class="csl">C grades</div></div>
            <div class="cs"><div class="csv" style="color:#ef4444">{dist['D/F']}</div><div class="csl">D/F</div></div>
          </div>
          <div class="ta-section">
            <div class="ta-title">TA Assignments</div>
            <table class="ta-table">
              <thead><tr><th>TA</th><th>Students</th><th>Avg Score</th></tr></thead>
              <tbody>{ta_rows}</tbody>
            </table>
          </div>
          <div class="links">
            <a href="{cs['dashboard_path']}">📊 Full Dashboard</a>
          </div>
        </div>"""

    total_students = sum(len(cs["results"]) for cs in course_summaries)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Combined Grading Overview</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f1f5f9;color:#1e293b;padding:32px 20px}}
.container{{max-width:1000px;margin:0 auto}}
.hdr{{background:linear-gradient(135deg,#1e1b4b,#4f46e5);color:#fff;border-radius:16px;padding:32px 36px;margin-bottom:26px}}
.hdr h1{{font-size:1.7rem;font-weight:800;margin-bottom:6px}}
.hdr p{{opacity:.8;font-size:.9rem}}
.top-stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:26px}}
.top-stat{{background:#fff;border-radius:12px;padding:22px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.top-stat-val{{font-size:2.2rem;font-weight:800;color:#4f46e5}}
.top-stat-lbl{{font-size:.75rem;color:#64748b;text-transform:uppercase;margin-top:4px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.course-card{{background:#fff;border-radius:14px;padding:24px;box-shadow:0 1px 4px rgba(0,0,0,.07)}}
.course-hdr{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px}}
.course-title{{font-size:1rem;font-weight:700;color:#1e293b}}
.course-code{{font-size:.78rem;color:#64748b;margin-top:3px}}
.course-avg{{font-size:2rem;font-weight:800}}
.course-stats{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:18px}}
.cs{{text-align:center;background:#f8fafc;border-radius:8px;padding:10px 4px}}
.csv{{font-size:1.2rem;font-weight:700;color:#4f46e5}}
.csl{{font-size:.7rem;color:#94a3b8;margin-top:2px}}
.ta-section{{margin-bottom:16px}}
.ta-title{{font-size:.78rem;text-transform:uppercase;color:#64748b;letter-spacing:.06em;margin-bottom:8px}}
.ta-table{{width:100%;border-collapse:collapse;font-size:.82rem}}
.ta-table th{{background:#f1f5ff;padding:7px 10px;text-align:left;color:#4f46e5;font-size:.75rem}}
.ta-table td{{padding:8px 10px;border-bottom:1px solid #f1f5f9}}
.ta-table tr:last-child td{{border:none}}
.links a{{display:inline-block;background:#eff6ff;color:#2563eb;padding:7px 14px;border-radius:8px;font-size:.82rem;text-decoration:none;font-weight:600}}
.links a:hover{{background:#dbeafe}}
footer{{text-align:center;color:#94a3b8;font-size:.78rem;margin-top:28px;padding-bottom:12px}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr}}.top-stats{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>
<div class="container">
  <div class="hdr">
    <h1>🎓 Combined Grading Overview</h1>
    <p>AI Grading Assistant · University of South Florida · {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
  </div>

  <div class="top-stats">
    <div class="top-stat"><div class="top-stat-val">{total_students}</div><div class="top-stat-lbl">Total Students</div></div>
    <div class="top-stat"><div class="top-stat-val">{len(course_summaries)}</div><div class="top-stat-lbl">Courses</div></div>
    <div class="top-stat"><div class="top-stat-val">{sum(len(ta_r) for cs in course_summaries for ta_r in cs['ta_assignments'].values())}</div><div class="top-stat-lbl">Graded</div></div>
  </div>

  <div class="grid">
    {course_cards}
  </div>

  <footer>AI Grading Assistant · University of South Florida · For TA Use Only</footer>
</div>
</body>
</html>"""


# ─── Single course pipeline ───────────────────────────────────────────────────

def run_course(
    api_key: str,
    course_name: str,
    assignment_name: str,
    instructions_path: str,
    rubric_path: str,
    submissions_folder: str,
    output_dir: Path,
    calibration_offset: float = 3.5,
    model: str = "claude-sonnet-4-6",
) -> Dict:
    """
    Grade a single course and produce all outputs.
    Returns a summary dict for the combined overview.
    """
    client = anthropic.Anthropic(api_key=api_key)
    cfg = COURSE_CONFIG.get(course_name, {"tas": ["TA1", "TA2"], "split": "equal"})

    print(f"\n{'='*60}")
    print(f"  COURSE: {course_name}")
    print(f"  Assignment: {assignment_name}")
    print(f"{'='*60}")

    # Load documents
    print(f"\n  Loading documents...")
    instructions_text = read_document(instructions_path)
    rubric_text = read_document(rubric_path)
    submissions = load_student_submissions(submissions_folder)
    print(f"    Instructions : {len(instructions_text):,} chars")
    print(f"    Rubric       : {len(rubric_text):,} chars")
    print(f"    Submissions  : {len(submissions)} student(s)")

    if not submissions:
        print(f"  ⚠️  No submissions found in {submissions_folder}. Skipping course.")
        return {}

    # Parse rubric
    print(f"\n  Parsing rubric...")
    criteria = parse_rubric(rubric_text, client)
    print(f"    Found {len(criteria)} criteria:")
    print(criteria_summary(criteria))

    # Grade all students
    print(f"\n  Grading {len(submissions)} student(s)...")
    output_dir.mkdir(parents=True, exist_ok=True)
    all_results = []
    student_ids = []

    for idx, sub in enumerate(submissions, start=1):
        student_id = f"Student_{idx:03d}"
        student_ids.append(student_id)
        print(f"    [{idx:02d}/{len(submissions)}] {student_id} ({sub['name']})...", end=" ", flush=True)

        try:
            result = grade_submission(
                client=client,
                model=model,
                criteria=criteria,
                assignment_name=assignment_name,
                course_name=course_name,
                instructions_text=instructions_text,
                submission=sub,
                student_id=student_id,
                calibration_offset=calibration_offset,
            )
            raw = result.get("total_score_raw", "?")
            cal = result.get("total_score", "?")
            max_s = result.get("max_score", "?")
            print(f"raw={raw}/{max_s}  calibrated={cal}/{max_s}  ({result.get('letter_grade','?')})")
        except Exception as e:
            print(f"ERROR: {e}")
            result = {
                "student_id": student_id, "student_name": sub["name"],
                "total_score": 0, "max_score": sum(c["max_points"] for c in criteria),
                "percentage": 0.0, "letter_grade": "F",
                "overall_feedback": f"Grading error: {e}",
                "criteria": [], "assignment_name": assignment_name,
                "course_name": course_name, "error": str(e),
            }

        # Save individual result
        with open(output_dir / f"{student_id}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        all_results.append(result)

        if idx < len(submissions):
            time.sleep(0.5)

    # Save combined results
    combined_path = output_dir / "all_results.json"
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    # Gold standard CSV template
    template_csv = output_dir / "gold_standard_template.csv"
    criterion_names = [c["name"] for c in criteria]
    create_gold_standard_template(str(template_csv), student_ids, criterion_names)

    # Per-course dashboard
    dashboard_html = build_dashboard(all_results, assignment_name=f"{course_name} — {assignment_name}")
    dashboard_path = output_dir / "dashboard.html"
    with open(dashboard_path, "w", encoding="utf-8") as f:
        f.write(dashboard_html)

    # TA assignment routing
    ta_assignments = assign_tas(all_results, cfg["tas"], cfg["split"])
    ta_dir = output_dir / "ta_assignments"
    ta_dir.mkdir(exist_ok=True)

    for ta_name, ta_results in ta_assignments.items():
        # Save TA JSON
        with open(ta_dir / f"{ta_name}_students.json", "w", encoding="utf-8") as f:
            json.dump(ta_results, f, indent=2)
        # Save TA HTML
        ta_html = build_ta_html(ta_name, course_name, ta_results)
        with open(ta_dir / f"{ta_name}_review.html", "w", encoding="utf-8") as f:
            f.write(ta_html)
        print(f"\n    {ta_name}: {len(ta_results)} students → {ta_dir / (ta_name + '_review.html')}")

    print(f"\n  Course outputs:")
    print(f"    all_results.json          → {combined_path}")
    print(f"    dashboard.html            → {dashboard_path}")
    print(f"    gold_standard_template    → {template_csv}")
    print(f"    ta_assignments/           → {ta_dir}/")

    return {
        "course_name": course_name,
        "assignment_name": assignment_name,
        "results": all_results,
        "ta_assignments": ta_assignments,
        "dashboard_path": str(dashboard_path.name),  # relative for HTML links
    }


# ─── Interactive setup ────────────────────────────────────────────────────────

def _prompt_path(label: str, must_exist: bool = True) -> str:
    while True:
        raw = input(f"  {label}: ").strip().strip('"')
        p = Path(raw)
        if not must_exist:
            return raw
        if p.exists():
            return raw
        print(f"    ✗ Not found: {p}")


def interactive_setup() -> dict:
    print("\n=== AI Grading Assistant — Multi-Course Runner ===\n")
    print("How many courses do you want to grade?")
    n_courses = input("  Courses (1 or 2): ").strip()
    n_courses = int(n_courses) if n_courses in ("1", "2") else 1

    cfg = {}
    for i in range(1, n_courses + 1):
        default_name = "AI for Analytics" if i == 1 else "Foundation of Business Statistics"
        print(f"\n── Course {i} ────────────────────────────────")
        name = input(f"  Course name (default: '{default_name}'): ").strip() or default_name
        assignment = input(f"  Assignment name (e.g. 'Lab 02'): ").strip() or "Assignment"
        instructions = _prompt_path("Instructions file (PDF/DOCX)")
        rubric = _prompt_path("Rubric file (PDF/DOCX)")
        submissions = _prompt_path("Submissions folder")
        cfg[f"course{i}"] = {
            "name": name, "assignment": assignment,
            "instructions": instructions, "rubric": rubric,
            "submissions": submissions,
        }

    output = _prompt_path("Output folder (will be created)", must_exist=False)
    offset = input("  Calibration offset (default 3.5): ").strip()
    offset = float(offset) if offset else 3.5

    return {"courses": cfg, "output": output, "offset": offset}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Grade both courses in one command")
    parser.add_argument("--course1-instructions")
    parser.add_argument("--course1-rubric")
    parser.add_argument("--course1-submissions")
    parser.add_argument("--course1-name",       default="AI for Analytics")
    parser.add_argument("--course1-assignment",  default="Assignment")
    parser.add_argument("--course2-instructions")
    parser.add_argument("--course2-rubric")
    parser.add_argument("--course2-submissions")
    parser.add_argument("--course2-name",       default="Foundation of Business Statistics")
    parser.add_argument("--course2-assignment",  default="Assignment")
    parser.add_argument("--output",             default="./grading_output")
    parser.add_argument("--offset",             type=float, default=3.5)
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Missing ANTHROPIC_API_KEY in environment or .env file")

    # Determine run mode
    cli_mode = bool(args.course1_instructions and args.course1_rubric and args.course1_submissions)

    if cli_mode:
        courses = []
        if args.course1_instructions:
            courses.append({
                "name": args.course1_name,
                "assignment": args.course1_assignment,
                "instructions": args.course1_instructions,
                "rubric": args.course1_rubric,
                "submissions": args.course1_submissions,
            })
        if args.course2_instructions:
            courses.append({
                "name": args.course2_name,
                "assignment": args.course2_assignment,
                "instructions": args.course2_instructions,
                "rubric": args.course2_rubric,
                "submissions": args.course2_submissions,
            })
        output_root = Path(args.output)
        calibration_offset = args.offset
    else:
        cfg = interactive_setup()
        courses = list(cfg["courses"].values())
        output_root = Path(cfg["output"])
        calibration_offset = cfg["offset"]

    output_root.mkdir(parents=True, exist_ok=True)

    # Run each course
    course_summaries = []
    for c in courses:
        course_output = output_root / c["name"].replace(" ", "_").replace("/", "_")
        summary = run_course(
            api_key=api_key,
            course_name=c["name"],
            assignment_name=c["assignment"],
            instructions_path=c["instructions"],
            rubric_path=c["rubric"],
            submissions_folder=c["submissions"],
            output_dir=course_output,
            calibration_offset=calibration_offset,
        )
        if summary:
            course_summaries.append(summary)

    # Combined overview
    if course_summaries:
        overview_html = build_combined_overview(course_summaries)
        overview_path = output_root / "combined_overview.html"
        with open(overview_path, "w", encoding="utf-8") as f:
            f.write(overview_html)

        total = sum(len(cs["results"]) for cs in course_summaries)
        print(f"\n{'='*60}")
        print(f"  ALL DONE — {total} students graded across {len(course_summaries)} course(s)")
        print(f"\n  Combined overview → {overview_path}")
        for cs in course_summaries:
            cdir = output_root / cs["course_name"].replace(" ", "_").replace("/", "_")
            print(f"  {cs['course_name']}")
            print(f"    Dashboard  → {cdir / 'dashboard.html'}")
            print(f"    TA folders → {cdir / 'ta_assignments/'}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
