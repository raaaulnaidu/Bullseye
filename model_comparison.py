"""
model_comparison.py
-------------------
Side-by-side comparison of frontier model (Claude Sonnet) vs local model (Ollama/Qwen)
on the same student submissions.

Produces:
  - Console summary table
  - comparison_report.html  — visual side-by-side for professor presentation

Usage:
    python model_comparison.py \\
        --frontier lab01_data/experiments/set2_results.json \\
        --local    lab01_data/output_local/all_results.json \\
        --output   lab01_data/comparison/

    # Optional labels
    python model_comparison.py \\
        --frontier lab01_data/experiments/set2_results.json \\
        --local    lab01_data/output_local/all_results.json \\
        --frontier-label "Claude Sonnet 4.6" \\
        --local-label    "Qwen2.5-7B (Ollama)" \\
        --output   lab01_data/comparison/
"""

import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_results(path: str) -> Dict[str, dict]:
    """Load a results JSON and return {student_id: result}."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {r["student_id"]: r for r in data}


def get_criteria_names(results: Dict[str, dict]) -> List[str]:
    """Extract criterion names from the first result."""
    for r in results.values():
        crit_list = r.get("rubric_criteria") or r.get("criteria", [])
        if crit_list:
            return [c["name"] for c in crit_list]
    return []


# ── Metrics ───────────────────────────────────────────────────────────────────

def compare(frontier: Dict[str, dict], local: Dict[str, dict]) -> dict:
    """Compute comparison metrics for all students present in both sets."""
    common = [sid for sid in frontier if sid in local]
    if not common:
        raise ValueError("No matching student IDs between the two result sets.")

    rows = []
    for sid in sorted(common):
        f_score = frontier[sid].get("total_score", 0)
        l_score = local[sid].get("total_score", 0)
        diff = l_score - f_score
        rows.append({
            "student_id": sid,
            "frontier":   f_score,
            "local":      l_score,
            "diff":       round(diff, 1),
            "agree":      abs(diff) <= 2,          # within 2 pts = agreement
            "f_grade":    frontier[sid].get("letter_grade", "—"),
            "l_grade":    local[sid].get("letter_grade",    "—"),
            "grade_agree": frontier[sid].get("letter_grade") == local[sid].get("letter_grade"),
        })

    f_scores = [r["frontier"] for r in rows]
    l_scores = [r["local"]    for r in rows]
    diffs    = [r["diff"]     for r in rows]
    max_score = next(iter(frontier.values())).get("max_score", 20)

    n = len(rows)
    return {
        "n":             n,
        "max_score":     max_score,
        "rows":          rows,
        "frontier_avg":  round(sum(f_scores) / n, 2),
        "local_avg":     round(sum(l_scores) / n, 2),
        "avg_gap":       round(sum(diffs)    / n, 2),  # local minus frontier
        "agree_pct":     round(sum(r["agree"] for r in rows) / n * 100, 1),
        "grade_agree_pct": round(sum(r["grade_agree"] for r in rows) / n * 100, 1),
        "max_diff":      max(diffs, key=abs),
        "within_1pt_pct": round(sum(1 for d in diffs if abs(d) <= 1) / n * 100, 1),
    }


# ── Console report ────────────────────────────────────────────────────────────

def print_report(stats: dict, fl: str, ll: str):
    n  = stats["n"]
    ms = stats["max_score"]
    w  = 65

    print("\n" + "=" * w)
    print(f"  MODEL COMPARISON — {fl}  vs  {ll}")
    print(f"  Generated : {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    print(f"  Students  : {n}   Max score: {ms}")
    print("=" * w)

    print(f"\n{'Student':<15} {'Frontier':>9} {'Local':>9} {'Diff':>7} {'Agree?':>8}")
    print(f"{'-'*15} {'-'*9} {'-'*9} {'-'*7} {'-'*8}")
    for r in stats["rows"]:
        tag = "  OK" if r["agree"] else "  !!"
        print(f"  {r['student_id']:<13} {r['frontier']:>6.1f}/{ms}  {r['local']:>6.1f}/{ms}  "
              f"{r['diff']:>+6.1f} {tag}")

    print(f"\n── SUMMARY ──────────────────────────────────────────────")
    print(f"  {fl:<28}  avg = {stats['frontier_avg']:.2f}/{ms}")
    print(f"  {ll:<28}  avg = {stats['local_avg']:.2f}/{ms}")
    print(f"  Avg gap (local − frontier)         : {stats['avg_gap']:+.2f} pts")
    print(f"  Within ±1 pt                       : {stats['within_1pt_pct']}%")
    print(f"  Within ±2 pts (agreement)          : {stats['agree_pct']}%")
    print(f"  Same letter grade                  : {stats['grade_agree_pct']}%")
    print(f"  Largest single-student gap         : {stats['max_diff']:+.1f} pts")

    print(f"\n── COST COMPARISON ──────────────────────────────────────")
    cost_f = n * 0.03
    print(f"  {fl:<28}  ~${cost_f:.2f}  (~$0.03/student)")
    print(f"  {ll:<28}  $0.00  (runs locally, no API cost)")
    print(f"  Savings with local model           : ~${cost_f:.2f}")
    print("=" * w + "\n")


# ── HTML report ───────────────────────────────────────────────────────────────

def build_html(stats: dict, fl: str, ll: str, assignment: str = "Lab 01") -> str:
    rows_html = ""
    for r in stats["rows"]:
        diff_color = "#16a34a" if abs(r["diff"]) <= 2 else "#dc2626"
        agree_badge = (
            '<span style="color:#16a34a;font-weight:600">Within ±2 pts</span>'
            if r["agree"] else
            '<span style="color:#dc2626;font-weight:600">Gap &gt; 2 pts</span>'
        )
        grade_badge = (
            '<span style="color:#16a34a">Same grade</span>'
            if r["grade_agree"] else
            f'<span style="color:#ea580c">{r["f_grade"]} → {r["l_grade"]}</span>'
        )
        rows_html += f"""
        <tr>
          <td><strong>{r['student_id']}</strong></td>
          <td style="text-align:center">{r['frontier']:.1f}</td>
          <td style="text-align:center">{r['f_grade']}</td>
          <td style="text-align:center">{r['local']:.1f}</td>
          <td style="text-align:center">{r['l_grade']}</td>
          <td style="text-align:center;color:{diff_color};font-weight:600">{r['diff']:+.1f}</td>
          <td style="text-align:center">{agree_badge}</td>
          <td style="text-align:center">{grade_badge}</td>
        </tr>"""

    ms  = stats["max_score"]
    n   = stats["n"]
    gap_color = "#16a34a" if abs(stats["avg_gap"]) <= 2 else "#ea580c"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Model Comparison — {assignment}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          margin: 0; padding: 2rem; background: #f8fafc; color: #1e293b; }}
  h1   {{ font-size: 1.6rem; margin-bottom: 0.25rem; }}
  .sub {{ color: #64748b; font-size: 0.9rem; margin-bottom: 2rem; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem; margin-bottom: 2rem; }}
  .card {{ background: #fff; border-radius: 10px; padding: 1.2rem 1.5rem;
           box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  .card .val  {{ font-size: 2rem; font-weight: 700; line-height: 1.1; }}
  .card .lbl  {{ font-size: 0.8rem; color: #64748b; margin-top: 0.3rem; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
           border-radius: 10px; overflow: hidden;
           box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  th    {{ background: #1e293b; color: #fff; padding: 0.75rem 1rem;
           text-align: left; font-size: 0.82rem; font-weight: 600; }}
  td    {{ padding: 0.7rem 1rem; border-bottom: 1px solid #f1f5f9;
           font-size: 0.88rem; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #f8fafc; }}
  .section {{ background: #fff; border-radius: 10px; padding: 1.5rem;
              box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-top: 1.5rem; }}
  .section h2 {{ font-size: 1rem; margin: 0 0 1rem; color: #475569; }}
  .cost-row {{ display: flex; justify-content: space-between;
               padding: 0.5rem 0; border-bottom: 1px solid #f1f5f9; }}
</style>
</head>
<body>
<h1>Frontier vs Local Model Comparison</h1>
<div class="sub">
  Assignment: <strong>{assignment}</strong> &nbsp;|&nbsp;
  {fl} vs {ll} &nbsp;|&nbsp;
  {n} students &nbsp;|&nbsp;
  Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
</div>

<div class="cards">
  <div class="card">
    <div class="val">{stats['frontier_avg']:.1f}<span style="font-size:1rem;color:#94a3b8">/{ms}</span></div>
    <div class="lbl">{fl} — avg score</div>
  </div>
  <div class="card">
    <div class="val">{stats['local_avg']:.1f}<span style="font-size:1rem;color:#94a3b8">/{ms}</span></div>
    <div class="lbl">{ll} — avg score</div>
  </div>
  <div class="card">
    <div class="val" style="color:{gap_color}">{stats['avg_gap']:+.2f}</div>
    <div class="lbl">Avg gap (local − frontier)</div>
  </div>
  <div class="card">
    <div class="val">{stats['agree_pct']}%</div>
    <div class="lbl">Students within ±2 pts</div>
  </div>
  <div class="card">
    <div class="val">{stats['grade_agree_pct']}%</div>
    <div class="lbl">Same letter grade</div>
  </div>
  <div class="card">
    <div class="val">{stats['within_1pt_pct']}%</div>
    <div class="lbl">Students within ±1 pt</div>
  </div>
</div>

<table>
  <thead>
    <tr>
      <th>Student</th>
      <th style="text-align:center">{fl}<br>Score /{ms}</th>
      <th style="text-align:center">Grade</th>
      <th style="text-align:center">{ll}<br>Score /{ms}</th>
      <th style="text-align:center">Grade</th>
      <th style="text-align:center">Diff</th>
      <th style="text-align:center">Score agreement</th>
      <th style="text-align:center">Grade agreement</th>
    </tr>
  </thead>
  <tbody>{rows_html}
  </tbody>
</table>

<div class="section">
  <h2>Cost Comparison (15 students)</h2>
  <div class="cost-row">
    <span>{fl}</span>
    <span><strong>~${n * 0.03:.2f}</strong> (~$0.03/student via Anthropic API)</span>
  </div>
  <div class="cost-row">
    <span>{ll}</span>
    <span><strong>$0.00</strong> (runs on your machine — no API cost)</span>
  </div>
  <div class="cost-row" style="border:none;font-weight:600;color:#16a34a">
    <span>Savings with local model</span>
    <span>~${n * 0.03:.2f} per assignment run</span>
  </div>
</div>

<div class="section">
  <h2>Key Takeaways</h2>
  <ul>
    <li>Average score gap between models: <strong>{stats['avg_gap']:+.2f} pts</strong></li>
    <li><strong>{stats['agree_pct']}%</strong> of students scored within ±2 pts of each other across both models</li>
    <li><strong>{stats['grade_agree_pct']}%</strong> of students received the same letter grade from both models</li>
    <li>Local model cost: <strong>$0</strong> — data never leaves the machine (full FERPA compliance)</li>
  </ul>
</div>
</body>
</html>"""


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Compare frontier vs local model grading results")
    parser.add_argument("--frontier",       required=True, help="Path to frontier model results JSON")
    parser.add_argument("--local",          required=True, help="Path to local model results JSON")
    parser.add_argument("--output",         default="lab01_data/comparison/")
    parser.add_argument("--frontier-label", default="Claude Sonnet 4.6")
    parser.add_argument("--local-label",    default="Qwen2.5-7B (Ollama)")
    parser.add_argument("--assignment",     default="CAI 3801 — Lab 01")
    args = parser.parse_args()

    frontier = load_results(args.frontier)
    local    = load_results(args.local)
    stats    = compare(frontier, local)

    fl = args.frontier_label
    ll = args.local_label

    print_report(stats, fl, ll)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    # Save JSON stats
    stats_path = out / "comparison_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)

    # Save HTML report
    html = build_html(stats, fl, ll, args.assignment)
    html_path = out / "comparison_report.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Report saved  → {html_path}")
    print(f"  Open in browser: file://{html_path.resolve()}\n")


if __name__ == "__main__":
    main()
