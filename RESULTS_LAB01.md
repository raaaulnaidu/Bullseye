# Results — Lab 01 Grading Evaluation (Set 2, Rubric-Calibrated)

**Dataset:** 15 CAI 3801 Lab 01 submissions, graded by the AI (Claude, Set 2 rubric-calibrated
prompt) and independently by a human TA against a 5-criterion, 20-point rubric.
**Note on n:** 14 are genuine student submissions; 1 (Student_011) was a non-submission — the
uploaded file was the blank assignment guide, which the AI correctly scored 0/20. The human
independently confirmed 0/20. It is retained as a valid *non-submission agreement* case and
excluded from calibration and from ranking correlation on completed work.

---

## 1. Finding 1 — Systematic negative bias (primary result)

The AI systematically under-scores relative to the human TA:

| Statistic | n=15 (incl. non-submission) | n=14 (completed work) |
|---|---|---|
| AI mean bias | **−3.60 pts** | **−3.86 pts** |
| t-test | t = −6.54, **p < 0.001** | p < 0.001 |
| MAE | 3.6 | 3.86 |

The bias is present in **every criterion** (Context −0.87, Understand table −1.17, Evidence
checks −0.83, Memo quality −0.53, AI Use Note −0.27) and is statistically significant. This
replicates the well-documented tendency of LLM graders to apply rubric language more strictly
than human raters (cf. Springer EAIT 2025). **This finding is robust — it does not depend on
any single data point.**

Qualitative inspection confirms the mechanism is *leniency*, not *comprehension*: the model's
per-criterion reasoning is specific and correct (it identifies real omissions such as a missing
negative sign, an invalid priority label, thin context fields), but it deducts points for
imperfections the human TA forgives as partial credit.

## 2. Finding 2 — Ranking agreement (report with care)

| Measure | Value | Scope |
|---|---|---|
| Pearson r | **0.648** | completed work only (n=14) — *defensible ranking estimate* |
| Pearson r | 0.906 | n=15 including the non-submission — inflated by one high-leverage point |
| QWK | 0.693 | n=15 — near published benchmark (0.68), but leverage-sensitive |

**We report r ≈ 0.65 on completed work as the ranking result.** The higher n=15 figures are
driven by the single (0,0) non-submission point anchoring the regression line; presenting them
as a ranking result would overstate the effect. Per-criterion correlations on the full set are
moderate-to-strong and less leverage-sensitive (Evidence checks 0.87, Understand table 0.78,
Memo quality 0.77).

**Limitation:** human grades have low variance (14 of 15 in the 18–20 range, σ = 0.89). This
supports the bias claim but limits ranking/agreement claims (QWK, Cohen's κ = undefined). A
future dataset with genuine grade spread is required to make a strong ranking claim.

## 3. Finding 3 — Calibration closes the gap and generalizes (mitigation)

A calibration offset, distributed proportionally across criteria and capped at each criterion's
maximum, was applied. Non-submissions (AI total = 0) are exempt so calibration never rewards
blank work. Validated by **leave-one-out cross-validation** (offset learned from the other
students, applied to the held-out one):

| Model | MAE | within ±2 pts |
|---|---|---|
| Raw AI (Set 2) | 3.60 | 26.7% |
| Calibrated — in-sample | 1.21 | 66.7% |
| **Calibrated — LOOCV (honest)** | **1.25** | **66.7%** |

Learned offset: **+3.86 pts**. Calibration reduces MAE by **~65%**, and the near-identical
in-sample vs LOOCV results confirm the correction **generalizes rather than overfits**.

**Residual:** `within ±1pt` is unchanged (66.7%) — the offset removes systematic bias but not
per-student disagreement. Students 003 and 005 (human 17–19, raw AI 11) remain ~4 pts off after
calibration; these reflect genuine AI–human disagreement on partial credit, not bias, and are
the ceiling on what calibration alone can fix.

## 4. Finding 4 — Non-submission detection (capability)

The AI correctly identified a blank/guide-only file as containing no student work and scored it
0/20 with a clear, actionable explanation — matching the human judgment. This suggests an
agentic grading assistant can reliably flag missing or non-genuine submissions for TA review, a
capability not evaluated in the comparator literature.

---

## Reproducibility

```
# Bias / correlation / QWK
python evaluator.py --human lab01_data/output/gold_standard_template.csv \
                    --ai lab01_data/experiments/set2_results.json

# Calibration (raw vs in-sample vs LOOCV)
python calibration_experiment.py --ai lab01_data/experiments/set2_results.json \
                                 --human lab01_data/output/gold_standard_template.csv
```

*Generated July 2026. Numbers regenerate from the commands above.*