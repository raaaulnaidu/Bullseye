"""
evaluator.py
------------
Evaluation framework: compares AI grading output against a human TA
gold standard, computes consistency metrics, and generates a report.

Workflow:
  1. Human TA fills in the gold standard CSV template.
  2. Run the grader to produce all_results.json.
  3. Call evaluate() to compute metrics and write a report.

Usage:
    python evaluator.py \
        --human  lab01_data/output/gold_standard.csv \
        --ai     lab01_data/output/all_results.json \
        --output lab01_data/output/evaluation_report.txt
"""

import argparse
import csv
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Default criteria for backward compatibility with Lab 01 results.
# When loading from all_results.json the criteria are read dynamically from the file.
_DEFAULT_CRITERIA     = ["Context", "Understand table", "Evidence checks", "Memo quality", "AI Use Note"]
_DEFAULT_CRITERIA_MAX = {"Context": 4, "Understand table": 5, "Evidence checks": 6, "Memo quality": 4, "AI Use Note": 1}
_DEFAULT_TOTAL_MAX    = 20

CRITERIA    = _DEFAULT_CRITERIA
CRITERIA_MAX = _DEFAULT_CRITERIA_MAX
TOTAL_MAX   = _DEFAULT_TOTAL_MAX


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_human_grades(csv_path: str) -> Dict[str, Dict]:
    """
    Load the human-graded gold standard CSV.

    Expected columns:
        student_id | Context | Understand table | Evidence checks | Memo quality | AI Use Note | notes

    Returns:
        {student_id: {criterion: float, "total": float}}
    """
    grades: Dict[str, Dict] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get("student_id", "").strip()
            if not sid:
                continue
            entry: Dict[str, float] = {}
            for c in CRITERIA:
                val = row.get(c, "").strip()
                if val:
                    entry[c] = float(val)
            if entry:
                entry["total"] = sum(entry.values())
                grades[sid] = entry
    return grades


def load_ai_grades(json_path: str) -> Dict[str, Dict]:
    """
    Load AI grading results from all_results.json.
    Auto-detects criteria from the file — works with any assignment.

    Returns:
        {student_id: {criterion: float, "total": float}}
    """
    global CRITERIA, CRITERIA_MAX, TOTAL_MAX

    with open(json_path, encoding="utf-8") as f:
        results = json.load(f)

    # Auto-detect criteria from the first result that has them
    for r in results:
        if r.get("rubric_criteria"):
            CRITERIA = [c["name"] for c in r["rubric_criteria"]]
            CRITERIA_MAX = {c["name"]: c["max_points"] for c in r["rubric_criteria"]}
            TOTAL_MAX = sum(c["max_points"] for c in r["rubric_criteria"])
            break
        if r.get("criteria"):
            detected = r["criteria"]
            CRITERIA = [c["name"] for c in detected]
            CRITERIA_MAX = {c["name"]: c.get("max_points", 0) for c in detected}
            TOTAL_MAX = sum(c.get("max_points", 0) for c in detected)
            break

    grades: Dict[str, Dict] = {}
    for r in results:
        sid = r.get("student_id", "").strip()
        criteria_map = {c["name"]: float(c.get("awarded_points", 0)) for c in r.get("criteria", [])}
        entry = {c: criteria_map.get(c, 0.0) for c in CRITERIA}
        entry["total"] = float(r.get("total_score", sum(entry.values())))
        grades[sid] = entry
    return grades


# ── Metric helpers ────────────────────────────────────────────────────────────

def _mae(h: List[float], a: List[float]) -> float:
    return sum(abs(x - y) for x, y in zip(h, a)) / len(h)

def _rmse(h: List[float], a: List[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(h, a)) / len(h))

def _within_n(h: List[float], a: List[float], n: float) -> float:
    return sum(1 for x, y in zip(h, a) if abs(x - y) <= n) / len(h) * 100

def _bias(h: List[float], a: List[float]) -> float:
    return sum(y - x for x, y in zip(h, a)) / len(h)

def _pearson(h: List[float], a: List[float]) -> float:
    n = len(h)
    if n < 2:
        return 0.0
    mh, ma = sum(h) / n, sum(a) / n
    num = sum((x - mh) * (y - ma) for x, y in zip(h, a))
    den = math.sqrt(sum((x - mh) ** 2 for x in h) * sum((y - ma) ** 2 for y in a))
    return num / den if den else 0.0

def _qwk(h: List[float], a: List[float], min_rating: int = 0, max_rating: int = None) -> float:
    """
    Quadratic Weighted Kappa between human (h) and AI (a) scores.

    Scores are rounded to the nearest integer to form ordinal rating categories
    spanning [min_rating, max_rating]. This is the standard agreement metric in
    the AES literature (e.g. ASAP), used here for direct comparability with
    published QWK figures (see RESEARCH_FINDINGS.md Section 3/4).
    """
    h_int = [int(round(x)) for x in h]
    a_int = [int(round(x)) for x in a]

    if max_rating is None:
        max_rating = max(max(h_int), max(a_int))

    num_ratings = max_rating - min_rating + 1
    if num_ratings <= 1:
        return 1.0

    observed = [[0] * num_ratings for _ in range(num_ratings)]
    h_hist   = [0] * num_ratings
    a_hist   = [0] * num_ratings
    for hi, ai in zip(h_int, a_int):
        hi = min(max(hi, min_rating), max_rating) - min_rating
        ai = min(max(ai, min_rating), max_rating) - min_rating
        observed[hi][ai] += 1
        h_hist[hi] += 1
        a_hist[ai] += 1

    n = len(h_int)
    numerator, denominator = 0.0, 0.0
    for i in range(num_ratings):
        for j in range(num_ratings):
            weight = ((i - j) ** 2) / ((num_ratings - 1) ** 2)
            expected = h_hist[i] * a_hist[j] / n
            numerator   += weight * observed[i][j]
            denominator += weight * expected

    return 1.0 if denominator == 0 else 1 - numerator / denominator


# ── Core evaluation ───────────────────────────────────────────────────────────

def compute_metrics(human_grades: Dict, ai_grades: Dict) -> Dict:
    """
    Compare AI grades to human grades for every student present in both.

    Returns a metrics dict with:
        n_students      — number of students evaluated
        per_criterion   — {criterion: {mae, rmse, within_1pt, exact_match_pct, bias, correlation}}
        overall         — same metrics for total scores, plus human_avg and ai_avg
        student_detail  — per-student score comparison list
    """
    common = [sid for sid in human_grades if sid in ai_grades]
    if not common:
        raise ValueError(
            "No common student IDs found. "
            "Check that student_id values in the CSV match the JSON."
        )

    metrics: Dict = {"n_students": len(common), "per_criterion": {}, "overall": {}}

    for c in CRITERIA:
        h_scores = [human_grades[sid][c] for sid in common if c in human_grades[sid]]
        a_scores = [ai_grades[sid][c]    for sid in common if c in ai_grades[sid]]
        if not h_scores:
            continue
        metrics["per_criterion"][c] = {
            "mae":             round(_mae(h_scores, a_scores), 3),
            "rmse":            round(_rmse(h_scores, a_scores), 3),
            "within_1pt_pct":  round(_within_n(h_scores, a_scores, 1.0), 1),
            "exact_match_pct": round(_within_n(h_scores, a_scores, 0.0), 1),
            "bias":            round(_bias(h_scores, a_scores), 3),
            "correlation":     round(_pearson(h_scores, a_scores), 3),
            "qwk":             round(_qwk(h_scores, a_scores, 0, CRITERIA_MAX[c]), 3),
            "max_points":      CRITERIA_MAX[c],
        }

    h_totals = [human_grades[sid]["total"] for sid in common]
    a_totals = [ai_grades[sid]["total"]    for sid in common]
    metrics["overall"] = {
        "mae":             round(_mae(h_totals, a_totals), 3),
        "rmse":            round(_rmse(h_totals, a_totals), 3),
        "within_1pt_pct":  round(_within_n(h_totals, a_totals, 1.0), 1),
        "within_2pt_pct":  round(_within_n(h_totals, a_totals, 2.0), 1),
        "exact_match_pct": round(_within_n(h_totals, a_totals, 0.0), 1),
        "bias":            round(_bias(h_totals, a_totals), 3),
        "correlation":     round(_pearson(h_totals, a_totals), 3),
        "qwk":             round(_qwk(h_totals, a_totals, 0, TOTAL_MAX), 3),
        "human_avg":       round(sum(h_totals) / len(h_totals), 2),
        "ai_avg":          round(sum(a_totals) / len(a_totals), 2),
    }
    metrics["student_detail"] = sorted(
        [
            {
                "student_id":   sid,
                "human_total":  human_grades[sid]["total"],
                "ai_total":     ai_grades[sid]["total"],
                "difference":   round(ai_grades[sid]["total"] - human_grades[sid]["total"], 1),
                "per_criterion": {
                    c: {
                        "human": human_grades[sid].get(c, "—"),
                        "ai":    ai_grades[sid].get(c, "—"),
                    }
                    for c in CRITERIA
                },
            }
            for sid in common
        ],
        key=lambda x: abs(x["difference"]),
        reverse=True,
    )
    return metrics


# ── Report writer ─────────────────────────────────────────────────────────────

def generate_report(metrics: Dict, output_path: str) -> str:
    """Write a plain-text evaluation report. Returns the output path."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    L = lines.append

    L("=" * 65)
    L("  GRADING EVALUATION REPORT — AI vs Human TA")
    L(f"  Generated : {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    L(f"  Students  : {metrics['n_students']}")
    L("=" * 65)

    ov = metrics["overall"]
    L("\n── OVERALL SCORE  (out of 20) ──────────────────────────────")
    L(f"  Human avg    : {ov['human_avg']:.2f}")
    L(f"  AI avg       : {ov['ai_avg']:.2f}")
    direction = "AI grades higher" if ov["bias"] > 0 else "AI grades lower"
    L(f"  AI bias      : {ov['bias']:+.3f} pts  ({direction})")
    L(f"  MAE          : {ov['mae']} pts")
    L(f"  RMSE         : {ov['rmse']} pts")
    L(f"  Within ±1pt  : {ov['within_1pt_pct']}%")
    L(f"  Within ±2pt  : {ov['within_2pt_pct']}%")
    L(f"  Exact match  : {ov['exact_match_pct']}%")
    L(f"  Pearson r    : {ov['correlation']}")
    L(f"  QWK          : {ov['qwk']}  (cf. published benchmark 0.68 — see RESEARCH_FINDINGS.md)")

    L("\n── PER-CRITERION METRICS ───────────────────────────────────")
    for c, m in metrics["per_criterion"].items():
        L(f"\n  {c}  (max {m['max_points']} pts)")
        L(f"    MAE          : {m['mae']} pts")
        L(f"    Bias         : {m['bias']:+.3f} pts")
        L(f"    Within ±1pt  : {m['within_1pt_pct']}%")
        L(f"    Exact match  : {m['exact_match_pct']}%")
        L(f"    Pearson r    : {m['correlation']}")
        L(f"    QWK          : {m['qwk']}")

    L("\n── STUDENT-LEVEL DETAIL  (sorted by disagreement) ─────────")
    L(f"  {'ID':<15} {'Human':>6} {'AI':>6} {'Diff':>6}")
    L(f"  {'-'*15} {'-'*6} {'-'*6} {'-'*6}")
    for d in metrics["student_detail"]:
        sign = "+" if d["difference"] >= 0 else ""
        L(f"  {d['student_id']:<15} {d['human_total']:>6.1f} {d['ai_total']:>6.1f} {sign}{d['difference']:>5.1f}")

    L("\n" + "=" * 65)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


# ── Template generator ────────────────────────────────────────────────────────

def create_gold_standard_template(
    output_path: str,
    student_ids: List[str],
    criteria_names: List[str] = None,
) -> str:
    """
    Generate an empty CSV for the human TA to fill in.
    Accepts any list of criterion names — defaults to the currently loaded CRITERIA.
    """
    cols = criteria_names if criteria_names else CRITERIA
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["student_id"] + cols + ["notes"])
        for sid in student_ids:
            writer.writerow([sid] + [""] * len(cols) + [""])
    return output_path


# ── CLI entry point ───────────────────────────────────────────────────────────

def evaluate(human_csv: str, ai_json: str, output_txt: str) -> Dict:
    human  = load_human_grades(human_csv)
    ai     = load_ai_grades(ai_json)
    metrics = compute_metrics(human, ai)
    generate_report(metrics, output_txt)
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate AI grading against human gold standard")
    parser.add_argument("--human",  required=True, help="Path to human-graded CSV (gold standard)")
    parser.add_argument("--ai",     required=True, help="Path to all_results.json from the grader")
    parser.add_argument("--output", default="lab01_data/output/evaluation_report.txt",
                        help="Where to save the evaluation report")
    args = parser.parse_args()

    metrics = evaluate(args.human, args.ai, args.output)
    ov = metrics["overall"]
    print(f"\n  Students evaluated : {metrics['n_students']}")
    print(f"  Overall MAE        : {ov['mae']} pts")
    print(f"  Within ±1 pt       : {ov['within_1pt_pct']}%")
    print(f"  Pearson r          : {ov['correlation']}")
    print(f"  QWK                : {ov['qwk']}")
    print(f"\n  Report saved to: {args.output}")
