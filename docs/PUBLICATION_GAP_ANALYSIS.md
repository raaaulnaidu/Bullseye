# BullsEye — Publication Gap Analysis

**Working title:** *Toward Agentic, Privacy-Preserving AI Grading: A Rubric-Calibrated Evaluation*
**Prepared for:** Immediate publication track
**Date:** July 2026

---

## 1. Positioning: two anchors, two jobs

| Role | Paper | What it gives us |
|---|---|---|
| **Framing anchor** | Johnston, Holtz, Martin, Ong, Tambe, Chatterji — *The Shift to Agentic AI: Evidence from Codex* (OpenAI/Columbia/Wharton/Duke, 2026) | Motivation and vocabulary: agentic AI is rapidly reshaping knowledge work (5× user growth in H1 2026; fastest uptake **outside** developers; concurrent agents; "skills"; 8+ hour tasks; large productivity/output gains; job reorganization). We use this to justify *why* an agentic grading assistant matters **now**. |
| **Methodological anchor** | *Automated Assignment Grading with LLMs: Insights from a Bioinformatics Course* (arXiv 2501.14499, 2025) | Structural template for the accuracy study: rubric + example answers, human-TA gold standard, per-assignment accuracy on ~119 students. Our Set 2 is structurally identical, so their method is our benchmark and our target sample size. |

**Why not anchor the whole paper on Codex:** it is an empirical usage / labor-economics study. Its evidence type is *adoption and output volume*, not *grading accuracy*. Anchoring an accuracy paper on it directly would be a forced fit. Instead it frames the Introduction and Discussion; the bioinformatics paper governs the Methods/Results.

**The one gap this pairing opens (our headline novelty):**
> Every existing AI-grading paper ([1]–[6] below) uses **single-shot LLM prompting**. The Codex paper documents **agentic** AI adoption but says nothing about **education/grading**. The intersection — an *agentic*, privacy-preserving grading assistant with a human-in-the-loop workflow — is empty in both literatures. That is our contribution.

---

## 2. Relevant papers (the "related work" set)

| # | Paper | Core claim | Sample |
|---|---|---|---|
| [1] | Bioinformatics LLM grading — arXiv 2501.14499 | Rubric + example answers → human-comparable accuracy | 119 students / 670 graded |
| [2] | RAG for short-answer grading — arXiv 2504.05276 | **Semantic** RAG improves agreement vs vanilla LLM | 124 responses |
| [3] | ChatGPT vs Claude essay scoring — Springer EAIT 2025 | Both models **stricter than humans**; Claude 3.5 strong | 117 essays |
| [4] | LLM essay grading (QWK) — ACM CSAI 2024 | QWK ≈ 0.68 with detailed rubric; drops sharply without | (paywalled) |
| [5] | Open-ended GenAI grading — Springer IJAIED 2025 | GPT-o1 near-human agreement but **expensive** | 110 students / 1,885 responses |
| [6] | LLM assessment RAG for HE — arXiv 2601.06141 | Curated course KB RAG beats generic grading | 701 essays |

---

## 3. Gap → experiment map (the core of the paper)

Each row: a gap in the literature, which BullsEye experiment/component addresses it, its status, and what's still needed to make it defensible.

| # | Gap in the literature | BullsEye evidence | Status | To make it defensible |
|---|---|---|---|---|
| **A** | **No agentic grading.** [1]–[6] are single-shot; Codex is agentic but not grading. | Multi-step pipeline (read → anonymize → retrieve → grade → evaluate); concurrent grading ([batch_grader.py](../batch_grader.py), [multi_course_runner.py](../multi_course_runner.py)); reusable "skills" ([rubric_library/](../rubric_library/)) | Partial — pipeline is scripted, not autonomous | Add an autonomous loop: self-critique → calibrate → **confidence-flag low-evidence grades for human review**. That closes the "agentic" claim. |
| **B** | **Semantic > keyword RAG**, per [2],[6]. | S3 used **keyword** RAG and underperformed (10.5 vs S2's 14.3). Set 5 tests **semantic** RAG on the same students. | Pending (Set 5 in [run_experiments.py](../run_experiments.py)) | Run Set 5; report S2 vs S3 vs S5 head-to-head on identical inputs. Cleanest gap→experiment match we have. |
| **C** | **Systematic LLM under-scoring / calibration**, confirmed by [3]. | **DONE (see [RESULTS_LAB01.md](RESULTS_LAB01.md)):** bias **−3.6 pts, p<0.001** across all criteria; calibration offset **+3.86** cuts MAE **3.6→1.25 (−65%)**, LOOCV-validated (generalizes, not overfit); non-submissions exempt. | ✅ Validated (n=15) | Strongest result. Optionally test whether a more lenient prompt reduces raw bias before calibration. |
| **D** | **Privacy-preserving architecture** — absent from [1]–[6]. Codex itself touts a "privacy-protecting pipeline." | Local PII stripping before any API/RAG call ([privacy_processor.py](../privacy_processor.py)); optional fully-local model. | Implemented | Report anonymization coverage (names/IDs/emails/etc.) and confirm zero PII egress. Strongest single differentiator. |
| **E** | **Frontier vs local/hosted cost–accuracy tradeoff** — [5] notes accuracy costs money, but no systematic grading comparison. | HF (Qwen2.5-7B) comparison; Ollama local option ([model_comparison.py](../model_comparison.py)). | Pending (HF run in [run_experiments.py](../run_experiments.py)) | Run HF + one local model on the same 15; report accuracy × cost × privacy × JSON-reliability. |
| **F** | **Calibrated few-shot** — [1] succeeds with example answers. | S4 few-shot **failed** (avg 1.7) using only high-scoring examples. | Failed → rebuild pending ([few_shot_builder.py](../few_shot_builder.py)) | Rebuild with **grade-spanning** examples (high/mid/low); the original failure is itself a reportable finding. |
| **G** | **Sample size + grade variance.** [1],[3],[5],[6] validate on 110–701 items. | **Full 15/15 now graded.** But human grades are low-variance (14/15 in 18–20, σ=0.89) — supports the *bias* claim, limits *ranking* claims (QWK/κ). | Partly closed | Queue the 100-student Summer 2026 run **with genuine grade spread** (include weaker work) to enable a defensible ranking claim. Biggest remaining weakness. |
| **H** | **Productivity / workforce evidence** — the Codex angle; [1]–[6] never measure grading time or TA workload. | *New:* log per-submission grading time → estimate **TA-hours saved** and throughput. | To collect (you confirmed feasible) | Add lightweight timing to the grading loop; report time/submission, class-level hours saved, and cost. **This is what connects our framing anchor to real evidence.** |

---

## 4. Recommended paper structure

1. **Introduction** — agentic AI is reshaping knowledge work (Codex framing); grading is a high-volume, privacy-sensitive knowledge task; no one has built agentic, privacy-preserving grading. *(Gap A + H framing)*
2. **Related Work** — the six grading papers, organized by rubric prompting / RAG / bias-calibration / cost. *(Anchor: [1])*
3. **System Design** — pipeline, privacy layer, RAG modes, calibration, concurrent/agentic execution, human-in-the-loop. *(Gaps A, D)*
4. **Experiments** — S1–S5 accuracy; semantic vs keyword RAG; calibration; frontier vs local; **productivity/time**. *(Gaps B, C, E, F, H)*
5. **Results** — MAE, RMSE, Pearson r, band accuracy, **QWK** (add for comparability with [4]), bias table, cost/time.
6. **Discussion** — when agentic + privacy-first grading helps; workforce/TA-workload implications (tie back to Codex). *(Gap A, H)*
7. **Limitations** — sample size (Gap G), single assignment, few-shot fragility.
8. **Conclusion.**

## 5. Critical path to a submittable draft

**Must-do (blocks the results section):**
1. ✅ Complete gold-standard grades for all 15 Lab 01 students *(Gap G)*
2. ✅ Run calibration validation and report raw vs calibrated LOOCV *(Gap C; see [RESULTS_LAB01.md](RESULTS_LAB01.md))*
3. ✅ Add QWK to [evaluator.py](../evaluator.py) output *(comparability with [4])*
4. Run Set 5 semantic RAG with the same provider/model as Set 2 *(Gap B)*
5. Add grading-time logging + TA-hours-saved estimate *(Gap H — the framing bridge)*

**High-value (strengthens novelty):**
6. Run HF + one local model on the same 15 *(Gap E)*
7. Rebuild calibrated few-shot with grade-spanning examples *(Gap F)*
8. ✅ Add confidence-flagging / human-handoff step to make the "agentic" claim real *(Gap A; implemented in `calibrated_grader.py` + Review Queue UI)*

**Target venues:** AIED, LAK (Learning Analytics & Knowledge), or EDUCAUSE Review (for the accessibility/workforce angle).
