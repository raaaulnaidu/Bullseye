"""
band_evaluator.py
-----------------
Evaluates AI grading accuracy across grade bands A / B / C.

Grade bands (out of 20 pts):
  Band A  →  90–100%  →  18–20 pts
  Band B  →  80–89%   →  16–17 pts
  Band C  →  70–79%   →  14–15 pts
  Below   →  < 70%    →  < 14 pts

Accuracy is measured as: did the AI assign the student to the same
band as the human TA? Expectation: highest accuracy for Band A
(clear excellent work), lower for borderline B/C cases.

Usage:
    python band_evaluator.py
    python band_evaluator.py --set 2
"""

import argparse
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple


TOTAL_MAX = 20

BANDS = {
    "A":  (90, 100, 18.0, 20.0, "#22c55e"),
    "B":  (80,  89, 16.0, 17.9, "#3b82f6"),
    "C":  (70,  79, 14.0, 15.9, "#f59e0b"),
    "D/F":(0,   69,  0.0, 13.9, "#ef4444"),
}


def assign_band(score: float, max_score: float = TOTAL_MAX) -> str:
    pct = (score / max_score) * 100
    if pct >= 90: return "A"
    if pct >= 80: return "B"
    if pct >= 70: return "C"
    return "D/F"


def load_results(json_path: str) -> Dict[str, float]:
    with open(json_path) as f:
        results = json.load(f)
    return {r["student_id"]: float(r.get("total_score", 0)) for r in results}


def load_human(csv_path: str) -> Dict[str, float]:
    human = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            sid = row.get("student_id", "").strip()
            if not sid: continue
            criteria = ["Context","Understand table","Evidence checks","Memo quality","AI Use Note"]
            total = sum(float(row.get(c, 0) or 0) for c in criteria)
            human[sid] = total
    return human


def compute_band_accuracy(
    human_scores: Dict[str, float],
    ai_scores: Dict[str, float],
) -> Dict:
    common = {sid for sid in human_scores if sid in ai_scores}
    if not common:
        raise ValueError("No common student IDs between human and AI results.")

    # Per-student band assignments
    details = []
    for sid in sorted(common):
        h_score = human_scores[sid]
        a_score = ai_scores[sid]
        h_band  = assign_band(h_score)
        a_band  = assign_band(a_score)
        match   = h_band == a_band
        details.append({
            "student_id":   sid,
            "human_score":  h_score,
            "ai_score":     a_score,
            "human_band":   h_band,
            "ai_band":      a_band,
            "correct_band": match,
            "off_by":       round(a_score - h_score, 1),
        })

    # Band-level accuracy
    band_stats = {}
    for band in ["A", "B", "C", "D/F"]:
        in_band = [d for d in details if d["human_band"] == band]
        correct = [d for d in in_band if d["correct_band"]]
        band_stats[band] = {
            "n_students": len(in_band),
            "n_correct":  len(correct),
            "accuracy":   round(len(correct) / len(in_band) * 100, 1) if in_band else None,
            "avg_human":  round(sum(d["human_score"] for d in in_band) / len(in_band), 2) if in_band else 0,
            "avg_ai":     round(sum(d["ai_score"]    for d in in_band) / len(in_band), 2) if in_band else 0,
            "avg_bias":   round(sum(d["off_by"] for d in in_band) / len(in_band), 2) if in_band else 0,
        }

    overall_correct = sum(1 for d in details if d["correct_band"])
    return {
        "n_total":    len(details),
        "overall_accuracy": round(overall_correct / len(details) * 100, 1),
        "band_stats": band_stats,
        "details":    details,
    }


def generate_band_report(metrics: Dict, output_path: str, set_label: str = "") -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    lines = []
    L = lines.append

    L("=" * 65)
    L("  GRADE BAND EVALUATION REPORT — AI vs Human TA")
    if set_label:
        L(f"  {set_label}")
    L(f"  Generated : {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    L("=" * 65)

    L(f"\n  Students evaluated : {metrics['n_total']}")
    L(f"  Overall band accuracy : {metrics['overall_accuracy']}%")

    L("\n── ACCURACY BY GRADE BAND ───────────────────────────────────")
    L(f"\n  {'Band':<8} {'Range':>10}  {'Students':>9}  {'Correct':>8}  {'Accuracy':>9}  {'Human Avg':>10}  {'AI Avg':>8}  {'AI Bias':>8}")
    L(f"  {'-'*8} {'-'*10}  {'-'*9}  {'-'*8}  {'-'*9}  {'-'*10}  {'-'*8}  {'-'*8}")

    band_ranges = {"A": "90–100%", "B": "80–89%", "C": "70–79%", "D/F": "< 70%"}
    for band in ["A", "B", "C", "D/F"]:
        bs = metrics["band_stats"][band]
        if bs["n_students"] == 0:
            L(f"  {band:<8} {band_ranges[band]:>10}  {'0':>9}  {'—':>8}  {'—':>9}  {'—':>10}  {'—':>8}  {'—':>8}")
            continue
        acc = f"{bs['accuracy']}%" if bs['accuracy'] is not None else "—"
        L(f"  {band:<8} {band_ranges[band]:>10}  {bs['n_students']:>9}  {bs['n_correct']:>8}  {acc:>9}  "
          f"{bs['avg_human']:>8.1f}/20  {bs['avg_ai']:>6.1f}/20  {bs['avg_bias']:>+7.1f}")

    L("\n── STUDENT DETAIL ───────────────────────────────────────────")
    L(f"\n  {'Student':<14} {'Human':>6} {'Band':>5}  {'AI':>6} {'Band':>5}  {'Match':>6}  {'Diff':>6}")
    L(f"  {'-'*14} {'-'*6} {'-'*5}  {'-'*6} {'-'*5}  {'-'*6}  {'-'*6}")
    for d in metrics["details"]:
        match_str = "✓" if d["correct_band"] else "✗"
        sign = "+" if d["off_by"] >= 0 else ""
        L(f"  {d['student_id']:<14} {d['human_score']:>6.1f} {d['human_band']:>5}  "
          f"{d['ai_score']:>6.1f} {d['ai_band']:>5}  {match_str:>6}  {sign}{d['off_by']:>5.1f}")

    L("\n── INTERPRETATION ───────────────────────────────────────────")
    L("  Band A accuracy should be highest: excellent work has clear,")
    L("  complete evidence that AI reliably detects.")
    L("  Band B/C accuracy is lower: borderline submissions have")
    L("  partial evidence that is harder to score consistently.")

    L("\n" + "=" * 65)

    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    return output_path


def generate_band_html(all_band_results: Dict, output_path: str) -> str:
    """Generate a visual HTML comparison of band accuracy across all sets."""

    rows_html = ""
    band_ranges = {"A": "90–100%", "B": "80–89%", "C": "70–79%", "D/F": "< 70%"}
    band_colors = {"A": "#22c55e", "B": "#3b82f6", "C": "#f59e0b", "D/F": "#ef4444"}

    for band in ["A", "B", "C", "D/F"]:
        cells = f'<td><span style="background:{band_colors[band]};color:#fff;padding:3px 10px;border-radius:12px;font-weight:700">{band}</span></td>'
        cells += f'<td>{band_ranges[band]}</td>'
        for set_num in sorted(all_band_results.keys()):
            bs = all_band_results[set_num]["band_stats"][band]
            if bs["n_students"] == 0:
                cells += "<td>—</td>"
            else:
                acc = bs["accuracy"]
                color = "#22c55e" if acc and acc >= 75 else "#f59e0b" if acc and acc >= 50 else "#ef4444"
                cells += f'<td style="font-weight:600;color:{color}">{acc}%<br><small style="color:#94a3b8;font-weight:400">{bs["n_correct"]}/{bs["n_students"]}</small></td>'
        rows_html += f"<tr>{cells}</tr>"

    set_headers = "".join(
        f'<th>Set {s}<br><small style="font-weight:400;color:#94a3b8">{["","Baseline","Rubric-Cal","Privacy+RAG","Few-Shot"][s]}</small></th>'
        for s in sorted(all_band_results.keys())
    )

    overall_row = '<tr style="background:#f8fafc"><td colspan="2" style="font-weight:700">Overall</td>'
    for s in sorted(all_band_results.keys()):
        oa = all_band_results[s]["overall_accuracy"]
        color = "#22c55e" if oa >= 75 else "#f59e0b" if oa >= 50 else "#ef4444"
        overall_row += f'<td style="font-weight:700;color:{color}">{oa}%</td>'
    overall_row += "</tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Grade Band Evaluation</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;color:#1e293b;padding:32px 20px}}
.container{{max-width:900px;margin:0 auto}}
.hdr{{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;border-radius:14px;padding:28px 32px;margin-bottom:24px}}
.hdr h1{{font-size:1.5rem;margin-bottom:4px}}
.hdr p{{opacity:.8;font-size:.88rem}}
.card{{background:#fff;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,.07)}}
.card h2{{font-size:.85rem;text-transform:uppercase;letter-spacing:.07em;color:#4f46e5;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;font-size:.88rem}}
th{{background:#f1f5ff;padding:10px 14px;text-align:left;color:#4f46e5;font-size:.78rem;text-transform:uppercase;border-bottom:2px solid #e2e8f0}}
td{{padding:11px 14px;border-bottom:1px solid #f1f5f9;vertical-align:middle}}
tr:last-child td{{border:none}}
.note{{background:#eff6ff;border-left:4px solid #3b82f6;border-radius:0 8px 8px 0;padding:12px 16px;font-size:.83rem;color:#1d4ed8;margin-top:16px}}
</style>
</head>
<body>
<div class="container">
<div class="hdr">
  <h1>📊 Grade Band Accuracy — AI vs Human TA</h1>
  <p>CAI 3801 Lab 01 · Generated {datetime.now().strftime('%B %d, %Y')}</p>
</div>

<div class="card">
  <h2>Band Accuracy by Experiment Set</h2>
  <table>
    <thead><tr><th>Band</th><th>Score Range</th>{set_headers}</tr></thead>
    <tbody>
      {rows_html}
      {overall_row}
    </tbody>
  </table>
  <div class="note">
    🎯 <strong>Expected pattern:</strong> Band A accuracy should be highest — excellent, complete submissions
    are the easiest for AI to identify correctly. Band B and C accuracy is typically lower because
    borderline submissions have partial evidence that the AI scores less consistently.
  </div>
</div>
</div>
</body>
</html>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)
    return output_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", type=int, default=2, help="Which experiment set to evaluate (default: 2)")
    parser.add_argument("--human", default="lab01_data/output/gold_standard_template.csv")
    args = parser.parse_args()

    human = load_human(args.human)
    print(f"Human grades loaded: {len(human)} students")

    all_band_results = {}
    for s in [1, 2, 3]:
        path = f"lab01_data/experiments/set{s}_results.json"
        if not Path(path).exists():
            continue
        ai = load_results(path)
        try:
            metrics = compute_band_accuracy(human, ai)
            all_band_results[s] = metrics
            out = f"lab01_data/experiments/band_report_set{s}.txt"
            generate_band_report(metrics, out, set_label=f"Set {s}")
            print(f"\nSet {s} overall band accuracy: {metrics['overall_accuracy']}%")
            for band in ["A", "B", "C", "D/F"]:
                bs = metrics["band_stats"][band]
                if bs["n_students"]:
                    print(f"  Band {band}: {bs['n_correct']}/{bs['n_students']} correct ({bs['accuracy']}%)")
        except ValueError as e:
            print(f"Set {s}: {e}")

    if all_band_results:
        html_path = "lab01_data/experiments/band_accuracy.html"
        generate_band_html(all_band_results, html_path)
        print(f"\nBand accuracy dashboard → {html_path}")
        import subprocess; subprocess.run(["open", html_path])


if __name__ == "__main__":
    main()
