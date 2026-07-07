"""
calibration_experiment.py
--------------------------
Tests whether a calibration offset closes the AI-human scoring gap, WITHOUT
overfitting. Reports raw vs calibrated accuracy two ways:

  * In-sample   : offset learned from all students (optimistic / circular).
  * LOOCV       : offset learned from the OTHER students for each held-out
                  student (honest estimate of generalization).

Offset is distributed proportionally across criteria and capped at each
criterion's max, mirroring CalibratedGrader._apply_calibration. Detected
non-submissions (AI total == 0) are exempt — calibration never rewards blanks.

Usage:
  python calibration_experiment.py \
      --ai lab01_data/experiments/set2_results.json \
      --human lab01_data/output/gold_standard_template.csv
"""

import argparse, csv, json

CRITERIA = ["Context", "Understand table", "Evidence checks", "Memo quality", "AI Use Note"]


def load(ai_path, human_path):
    ai = {r["student_id"]: r for r in json.load(open(ai_path))}
    human = {}
    for row in csv.DictReader(open(human_path)):
        sid = row["student_id"].strip()
        human[sid] = {c: float(row[c]) for c in CRITERIA}
        human[sid]["total"] = sum(human[sid][c] for c in CRITERIA)
    return ai, human


def ai_total(rec):
    return float(rec.get("total_score", 0))


def calibrate(rec, offset):
    """Apply offset proportionally across criteria, capped at each max. Returns calibrated total."""
    crit = rec.get("criteria", [])
    cmax_total = sum(c.get("max_points", 0) for c in crit)
    if cmax_total == 0:
        return ai_total(rec)
    total = 0.0
    for c in crit:
        cmax = c.get("max_points", 0)
        prop = offset * (cmax / cmax_total)
        total += min(cmax, c.get("awarded_points", 0) + prop)
    return round(total, 1)


def mae(pairs):   # pairs of (human, ai)
    return round(sum(abs(h - a) for h, a in pairs) / len(pairs), 3)


def within(pairs, tol):
    return round(100 * sum(1 for h, a in pairs if abs(h - a) <= tol) / len(pairs), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai", required=True)
    ap.add_argument("--human", required=True)
    args = ap.parse_args()
    ai, human = load(args.ai, args.human)

    ids = [s for s in human if s in ai]
    # Non-submissions: AI detected a 0. Exempt from calibration.
    real = [s for s in ids if ai_total(ai[s]) > 0]
    nonsub = [s for s in ids if ai_total(ai[s]) == 0]

    print(f"Students: {len(ids)}  |  real submissions: {len(real)}  |  non-submissions (exempt): {len(nonsub)} {nonsub}\n")

    # ---- RAW ----
    raw_pairs = [(human[s]["total"], ai_total(ai[s])) for s in ids]

    # ---- In-sample offset (learned from all real students) ----
    offset_all = sum(human[s]["total"] - ai_total(ai[s]) for s in real) / len(real)
    insample_pairs = []
    for s in ids:
        cal = ai_total(ai[s]) if s in nonsub else calibrate(ai[s], offset_all)
        insample_pairs.append((human[s]["total"], cal))

    # ---- LOOCV offset (honest) ----
    loocv_pairs = []
    loocv_by_id = {}
    for s in ids:
        if s in nonsub:
            cal = ai_total(ai[s])
            loocv_pairs.append((human[s]["total"], cal))
            loocv_by_id[s] = cal
            continue
        others = [o for o in real if o != s]
        off = sum(human[o]["total"] - ai_total(ai[o]) for o in others) / len(others)
        cal = calibrate(ai[s], off)
        loocv_pairs.append((human[s]["total"], cal))
        loocv_by_id[s] = cal

    print(f"Learned offset (in-sample, real students): +{offset_all:.2f} pts\n")
    print(f"{'Model':<28}{'MAE':>8}{'within ±1':>12}{'within ±2':>12}")
    print("-" * 60)
    print(f"{'Raw AI (Set 2)':<28}{mae(raw_pairs):>8}{within(raw_pairs,1):>11}%{within(raw_pairs,2):>11}%")
    print(f"{'Calibrated (in-sample)':<28}{mae(insample_pairs):>8}{within(insample_pairs,1):>11}%{within(insample_pairs,2):>11}%")
    print(f"{'Calibrated (LOOCV, honest)':<28}{mae(loocv_pairs):>8}{within(loocv_pairs,1):>11}%{within(loocv_pairs,2):>11}%")
    print()
    print("Per-student (human | raw -> calibrated LOOCV):")
    for s in sorted(ids):
        h = human[s]["total"]; r = ai_total(ai[s]); c = loocv_by_id[s]
        tag = "  (non-submission, exempt)" if s in nonsub else ""
        print(f"  {s}: {h:>5} | {r:>5} -> {c:>5}{tag}")


if __name__ == "__main__":
    main()
