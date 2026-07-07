"""
run_fewshot_experiment.py
-------------------------
Rigorous few-shot test (Gap F), fixing the flaws in the original Set 4:

  1. Examples use HUMAN gold-standard scores as targets (not the AI's own biased
     scores) — so few-shot can actually reduce the -3.6 bias, not reinforce it.
  2. Example students are HELD OUT of the test set (no train/test leakage).
  3. Each test student is graded TWICE with identical config — once without
     examples (baseline), once with few-shot — so few-shot is the only variable.

Exemplars (held out): the little grade spread this dataset has —
  Student_001 (human 20, high) · Student_005 (human 17, lowest real) ·
  Student_011 (human 0, non-submission).

Everything else: claude-sonnet-4-6, full_context (Set 2 approach), offset 0.

Usage:  python run_fewshot_experiment.py
"""

import json, os, csv, copy
from pathlib import Path

INSTRUCTIONS  = "lab01_data/source_files/CAI3801_Lab01_StepByStep_Guide.pdf"
CRITERIA_JSON = "lab01_data/source_files/lab01_criteria.json"
SUBMISSIONS   = "lab01_data/student_submissions/"
SET2_RESULTS  = "lab01_data/experiments/set2_results.json"
HUMAN_CSV     = "lab01_data/output/gold_standard_template.csv"
CRITERIA_COLS = ["Context", "Understand table", "Evidence checks", "Memo quality", "AI Use Note"]
EXEMPLARS     = {"Student_001": "high", "Student_005": "low", "Student_011": "low"}
OUT_DIR       = Path("lab01_data/experiments/fewshot")


def load_env():
    env = Path(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def human_grades():
    h = {}
    for row in csv.DictReader(open(HUMAN_CSV)):
        sid = row["student_id"].strip()
        h[sid] = {c: float(row[c]) for c in CRITERIA_COLS}
        h[sid]["total"] = sum(h[sid][c] for c in CRITERIA_COLS)
    return h


def build_human_examples(set2, human):
    """One example per exemplar: Set 2's descriptive feedback, but HUMAN scores as the target."""
    s2 = {r["student_id"]: r for r in set2}
    examples = []
    for sid, band in EXEMPLARS.items():
        result = copy.deepcopy(s2[sid])
        for c in result.get("criteria", []):
            c["awarded_points"] = human[sid][c["name"]]          # <-- human target
        result["total_score"] = human[sid]["total"]
        for k in ("percentage", "consistency_notes"):
            result.pop(k, None)
        evidence = "\n".join(
            f"[{c['name']}] {c.get('completed','')}" for c in result.get("criteria", [])
        )
        examples.append({"student_id": sid, "grade_band": band, "evidence": evidence, "result": result})
    return examples


def main():
    load_env()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ERROR: ANTHROPIC_API_KEY not found in .env"); return

    from document_reader import read_document, load_student_submissions
    from calibrated_grader import CalibratedGrader

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    criteria = json.load(open(CRITERIA_JSON))
    set2 = json.load(open(SET2_RESULTS))
    human = human_grades()
    examples = build_human_examples(set2, human)

    instructions = read_document(INSTRUCTIONS)
    subs = load_student_submissions(SUBMISSIONS)
    test = [(f"Student_{i:03d}", s) for i, s in enumerate(subs, 1)
            if f"Student_{i:03d}" not in EXEMPLARS]

    print(f"Exemplars (held out): {list(EXEMPLARS)}")
    print(f"Test students: {len(test)}  |  grading each twice (baseline + few-shot)\n")

    def make_grader(with_examples):
        return CalibratedGrader(
            criteria=criteria, assignment_name="Lab01 few-shot experiment",
            model="claude-sonnet-4-6", provider="anthropic", api_key=key,
            evidence_mode="full_context", calibration_offset=0.0,
            few_shot_examples=examples if with_examples else None,
        )
    baseline_grader, fewshot_grader = make_grader(False), make_grader(True)

    rows = []
    for sid, sub in test:
        line = {"student_id": sid, "human": human[sid]["total"]}
        for arm, grader in (("baseline", baseline_grader), ("fewshot", fewshot_grader)):
            try:
                r = grader.grade_submission(instructions, sub["text"], sid, sub["name"])
                (OUT_DIR / f"{sid}_{arm}.json").write_text(json.dumps(r, indent=2))
                line[arm] = r.get("total_score", 0)
            except Exception as e:
                line[arm] = None
                print(f"  {sid} {arm} ERROR: {str(e)[:80]}")
        print(f"  {sid}: human={line['human']:>4}  baseline={line['baseline']}  fewshot={line['fewshot']}")
        rows.append(line)

    (OUT_DIR / "summary.json").write_text(json.dumps(rows, indent=2))

    def stats(arm):
        pairs = [(r["human"], r[arm]) for r in rows if r.get(arm) is not None]
        n = len(pairs)
        bias = sum(a - h for h, a in pairs) / n
        mae = sum(abs(h - a) for h, a in pairs) / n
        return n, bias, mae

    print("\n=== RESULT (test students only, raw scores, no calibration) ===")
    print(f"{'Arm':<12}{'n':>4}{'bias':>9}{'MAE':>9}")
    for arm in ("baseline", "fewshot"):
        n, bias, mae = stats(arm)
        print(f"{arm:<12}{n:>4}{bias:>+9.2f}{mae:>9.2f}")
    print(f"\nSaved → {OUT_DIR}/summary.json")


if __name__ == "__main__":
    main()
