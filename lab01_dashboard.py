"""
lab01_dashboard.py
------------------
Generates a self-contained HTML dashboard from all_results.json.
Open the output HTML file in any browser — no server needed.

Usage:
    python lab01_dashboard.py
    python lab01_dashboard.py --input lab01_data/output/all_results.json
                              --output lab01_data/output/dashboard.html
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict


CRITERIA       = ["Context", "Understand table", "Evidence checks", "Memo quality", "AI Use Note"]
CRITERIA_MAX   = [4, 5, 6, 4, 1]
CRITERIA_ABBR  = ["Context", "Understand", "Evidence", "Memo", "AI Note"]
TOTAL_MAX      = 20


def _grade_color(pct: float) -> str:
    if pct >= 80: return "#22c55e"
    if pct >= 60: return "#3b82f6"
    if pct >= 40: return "#f59e0b"
    return "#ef4444"


def _letter(pct: float) -> str:
    if pct >= 95: return "A+"
    if pct >= 90: return "A"
    if pct >= 85: return "A-"
    if pct >= 80: return "B+"
    if pct >= 75: return "B"
    if pct >= 70: return "B-"
    if pct >= 65: return "C+"
    if pct >= 60: return "C"
    if pct >= 55: return "C-"
    if pct >= 50: return "D"
    return "F"


def build_dashboard(results: List[Dict], assignment_name: str = "CAI 3801 — Lab 01") -> str:
    valid   = [r for r in results if not all(c.get("awarded_points", 0) == 0 for c in r.get("criteria", []))]
    all_pct = [r["total_score"] / TOTAL_MAX * 100 for r in results]
    avg_pct = round(sum(all_pct) / len(all_pct), 1) if all_pct else 0
    highest = max(all_pct) if all_pct else 0
    lowest  = min(all_pct) if all_pct else 0
    passing = sum(1 for p in all_pct if p >= 60)

    # Per-criterion averages
    crit_avgs = []
    for i, cname in enumerate(CRITERIA):
        scores = [r["criteria"][i]["awarded_points"] for r in results if len(r.get("criteria", [])) > i]
        crit_avgs.append(round(sum(scores) / len(scores), 2) if scores else 0)

    # Score distribution buckets
    buckets = {"0–24%": 0, "25–49%": 0, "50–74%": 0, "75–89%": 0, "90–100%": 0}
    for p in all_pct:
        if p < 25:   buckets["0–24%"]   += 1
        elif p < 50: buckets["25–49%"]  += 1
        elif p < 75: buckets["50–74%"]  += 1
        elif p < 90: buckets["75–89%"]  += 1
        else:        buckets["90–100%"] += 1

    # Student bars data (sorted descending)
    sorted_results = sorted(results, key=lambda r: r["total_score"], reverse=True)
    student_labels = json.dumps([r["student_id"] for r in sorted_results])
    student_scores = json.dumps([r["total_score"] for r in sorted_results])
    student_colors = json.dumps([_grade_color(r["total_score"] / TOTAL_MAX * 100) for r in sorted_results])

    # Student cards HTML
    cards_html = ""
    for r in results:
        sid   = r.get("student_id", "")
        total = r.get("total_score", 0)
        pct   = round(total / TOTAL_MAX * 100, 1)
        color = _grade_color(pct)
        grade = _letter(pct)

        crit_pills = ""
        for c in r.get("criteria", []):
            cp = round(c["awarded_points"] / c["max_points"] * 100) if c["max_points"] else 0
            cc = _grade_color(cp)
            crit_pills += f'<span class="pill" style="border-color:{cc};color:{cc}">{c["name"].split()[0]} {c["awarded_points"]}/{c["max_points"]}</span>'

        crit_rows = ""
        for c in r.get("criteria", []):
            cp    = round(c["awarded_points"] / c["max_points"] * 100) if c["max_points"] else 0
            cc    = _grade_color(cp)
            crit_rows += f"""
            <tr>
              <td class="cn">{c['name']}</td>
              <td><span style="color:{cc};font-weight:600">{c['awarded_points']}/{c['max_points']}</span></td>
              <td class="fb">{c.get('completed','')}</td>
              <td class="fb">{c.get('missing_or_weak','')}</td>
              <td class="fb">{c.get('suggestion','')}</td>
            </tr>"""

        cards_html += f"""
        <div class="card" id="{sid}">
          <div class="card-hdr" onclick="toggle('{sid}')">
            <div class="card-left">
              <span class="sid">{sid}</span>
              <div class="pills">{crit_pills}</div>
            </div>
            <div class="card-right">
              <div class="score-ring" style="--c:{color}">
                <span class="ring-score">{total}</span>
                <span class="ring-max">/20</span>
              </div>
              <span class="grade-badge" style="background:{color}">{grade}</span>
              <span class="chevron" id="chev-{sid}">▼</span>
            </div>
          </div>
          <div class="card-body" id="body-{sid}" style="display:none">
            <div class="score-bar-wrap">
              <div class="score-bar-fill" style="width:{pct}%;background:{color}"></div>
            </div>
            <p class="overall">{r.get('overall_feedback','')}</p>
            <div class="tbl-wrap">
              <table class="crit-table">
                <thead><tr>
                  <th>Criterion</th><th>Score</th>
                  <th>Completed</th><th>Missing / Weak</th><th>Suggestion</th>
                </tr></thead>
                <tbody>{crit_rows}</tbody>
              </table>
            </div>
            {"<div class='consistency'>📋 " + r.get('consistency_notes','') + "</div>" if r.get('consistency_notes') else ""}
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{assignment_name} — Grading Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f1f5f9;color:#1e293b}}
.container{{max-width:1100px;margin:0 auto;padding:28px 18px}}

/* ── Header ── */
.hdr{{background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%);color:#fff;border-radius:16px;padding:32px 36px;margin-bottom:26px}}
.hdr h1{{font-size:1.75rem;font-weight:700;margin-bottom:4px}}
.hdr p{{opacity:.8;font-size:.9rem}}

/* ── Stat cards ── */
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:26px}}
.stat{{background:#fff;border-radius:12px;padding:20px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.stat-val{{font-size:2rem;font-weight:700;color:#4f46e5}}
.stat-lbl{{font-size:.75rem;color:#64748b;margin-top:3px;text-transform:uppercase;letter-spacing:.05em}}

/* ── Charts row ── */
.charts{{display:grid;grid-template-columns:1.6fr 1fr;gap:18px;margin-bottom:26px}}
.chart-card{{background:#fff;border-radius:12px;padding:22px;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.chart-card h3{{font-size:.85rem;text-transform:uppercase;color:#64748b;letter-spacing:.06em;margin-bottom:16px}}

/* ── Per-student bar chart ── */
.full-chart{{background:#fff;border-radius:12px;padding:22px;box-shadow:0 1px 3px rgba(0,0,0,.07);margin-bottom:26px}}
.full-chart h3{{font-size:.85rem;text-transform:uppercase;color:#64748b;letter-spacing:.06em;margin-bottom:16px}}

/* ── Student cards ── */
.section-title{{font-size:.8rem;text-transform:uppercase;color:#94a3b8;letter-spacing:.08em;margin-bottom:12px}}
.card{{background:#fff;border-radius:12px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.07);overflow:hidden}}
.card-hdr{{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;cursor:pointer;user-select:none}}
.card-hdr:hover{{background:#f8fafc}}
.card-left{{display:flex;flex-direction:column;gap:6px}}
.sid{{font-weight:700;font-size:1rem;color:#1e293b}}
.pills{{display:flex;flex-wrap:wrap;gap:5px}}
.pill{{font-size:.72rem;padding:2px 8px;border-radius:20px;border:1.5px solid;font-weight:600}}
.card-right{{display:flex;align-items:center;gap:12px}}
.score-ring{{display:flex;align-items:baseline;gap:2px}}
.ring-score{{font-size:1.6rem;font-weight:700;color:var(--c)}}
.ring-max{{font-size:.85rem;color:#94a3b8}}
.grade-badge{{padding:4px 12px;border-radius:20px;color:#fff;font-weight:700;font-size:.9rem}}
.chevron{{color:#cbd5e1;font-size:.9rem}}

.card-body{{padding:0 20px 20px;border-top:1px solid #f1f5f9}}
.score-bar-wrap{{background:#f1f5f9;border-radius:10px;height:7px;margin:14px 0 12px}}
.score-bar-fill{{height:7px;border-radius:10px;transition:width .4s}}
.overall{{color:#475569;line-height:1.65;font-size:.9rem;margin-bottom:16px}}

.tbl-wrap{{overflow-x:auto}}
.crit-table{{width:100%;border-collapse:collapse;font-size:.83rem}}
.crit-table th{{background:#f8fafc;padding:8px 10px;text-align:left;color:#64748b;font-size:.78rem;border-bottom:2px solid #e2e8f0}}
.crit-table td{{padding:9px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top}}
.crit-table tr:last-child td{{border:none}}
.cn{{font-weight:600;white-space:nowrap;color:#334155}}
.fb{{color:#475569;line-height:1.5}}
.consistency{{background:#eff6ff;border-left:4px solid #3b82f6;border-radius:0 8px 8px 0;padding:10px 14px;margin-top:14px;font-size:.82rem;color:#1d4ed8}}

footer{{text-align:center;color:#94a3b8;font-size:.78rem;margin-top:28px;padding-bottom:12px}}
@media(max-width:700px){{
  .stats{{grid-template-columns:repeat(2,1fr)}}
  .charts{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>
<div class="container">

  <div class="hdr">
    <h1>📊 {assignment_name}</h1>
    <p>AI Grading Dashboard &nbsp;·&nbsp; Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
  </div>

  <div class="stats">
    <div class="stat"><div class="stat-val">{len(results)}</div><div class="stat-lbl">Students</div></div>
    <div class="stat"><div class="stat-val">{avg_pct}%</div><div class="stat-lbl">Class Average</div></div>
    <div class="stat"><div class="stat-val">{highest:.0f}%</div><div class="stat-lbl">Highest Score</div></div>
    <div class="stat"><div class="stat-val">{passing}/{len(results)}</div><div class="stat-lbl">Passing (≥60%)</div></div>
  </div>

  <div class="charts">
    <div class="chart-card">
      <h3>Average Score per Criterion</h3>
      <canvas id="critChart" height="200"></canvas>
    </div>
    <div class="chart-card">
      <h3>Score Distribution</h3>
      <canvas id="distChart" height="200"></canvas>
    </div>
  </div>

  <div class="full-chart">
    <h3>Per-Student Total Scores (out of {TOTAL_MAX})</h3>
    <canvas id="studentChart" height="120"></canvas>
  </div>

  <p class="section-title">Student Results — click a row to expand</p>
  {cards_html}

  <footer>CAI 3801 Lab 01 · AI Grading Dashboard · For TA Use Only</footer>
</div>

<script>
// ── Criterion average chart ──────────────────────────────────────
new Chart(document.getElementById('critChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(CRITERIA_ABBR)},
    datasets: [
      {{
        label: 'AI Average',
        data: {json.dumps(crit_avgs)},
        backgroundColor: '#6366f1cc',
        borderColor: '#4f46e5',
        borderWidth: 2,
        borderRadius: 6,
      }},
      {{
        label: 'Max Points',
        data: {json.dumps(CRITERIA_MAX)},
        backgroundColor: '#e2e8f0',
        borderColor: '#cbd5e1',
        borderWidth: 1,
        borderRadius: 6,
      }}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }} }} }} }},
    scales: {{
      y: {{ beginAtZero: true, grid: {{ color: '#f1f5f9' }}, ticks: {{ stepSize: 1 }} }},
      x: {{ grid: {{ display: false }} }}
    }}
  }}
}});

// ── Distribution donut ───────────────────────────────────────────
new Chart(document.getElementById('distChart'), {{
  type: 'doughnut',
  data: {{
    labels: {json.dumps(list(buckets.keys()))},
    datasets: [{{
      data: {json.dumps(list(buckets.values()))},
      backgroundColor: ['#ef4444','#f97316','#f59e0b','#3b82f6','#22c55e'],
      borderWidth: 2,
      borderColor: '#fff',
    }}]
  }},
  options: {{
    responsive: true,
    cutout: '62%',
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }} }} }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.label}}: ${{ctx.raw}} student${{ctx.raw !== 1 ? 's' : ''}}` }} }}
    }}
  }}
}});

// ── Per-student bar chart ────────────────────────────────────────
new Chart(document.getElementById('studentChart'), {{
  type: 'bar',
  data: {{
    labels: {student_labels},
    datasets: [{{
      label: 'Total Score',
      data: {student_scores},
      backgroundColor: {student_colors},
      borderRadius: 5,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      y: {{ beginAtZero: true, max: {TOTAL_MAX}, grid: {{ color: '#f1f5f9' }},
             title: {{ display: true, text: 'Score / {TOTAL_MAX}', font: {{ size: 11 }} }} }},
      x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 11 }} }} }}
    }}
  }}
}});

// ── Card toggle ──────────────────────────────────────────────────
function toggle(sid) {{
  const body  = document.getElementById('body-'  + sid);
  const chev  = document.getElementById('chev-'  + sid);
  const open  = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  chev.textContent   = open ? '▼' : '▲';
}}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate grading dashboard HTML")
    parser.add_argument("--input",  default="lab01_data/output/all_results.json")
    parser.add_argument("--output", default="lab01_data/output/dashboard.html")
    parser.add_argument("--title",  default="CAI 3801 — Lab 01")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        results = json.load(f)

    html = build_dashboard(results, assignment_name=args.title)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard saved → {args.output}")
    print(f"Open in browser: file://{Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
