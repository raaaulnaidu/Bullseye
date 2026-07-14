# BullsEye: Faculty Setup and Publication Brief

**Project:** BullsEye, a privacy-aware AI grading assistant  
**Prepared:** July 2026  
**Primary goal:** Enable a faculty collaborator to run the repository locally and review the current research direction for an immediate publication.

---

## Executive Summary

BullsEye is an AI-assisted grading system designed for university teaching assistant workflows. The system grades student submissions against an instructor rubric, generates structured feedback, anonymizes sensitive student information before cloud model calls, and evaluates AI grades against a human gold standard.

The current Lab 01 experiment shows that the raw AI grader systematically under-scores relative to the human TA, but a simple calibration step substantially improves agreement. This creates a focused publication opportunity around **rubric-based LLM grading, privacy-aware grading workflows, human-in-the-loop review, and calibration against human judgment**.

The repository is set up so a collaborator can run the app locally, test it with synthetic demo data, and reproduce the current evaluation pipeline.

---

## What BullsEye Does

BullsEye supports the following grading workflow:

```text
assignment + rubric + submissions
        -> document parsing
        -> privacy anonymization
        -> rubric-aware AI grading
        -> structured feedback
        -> human review
        -> model evaluation and calibration
```

Core capabilities:

- Upload assignment instructions, grading rubric, and student submissions.
- Grade submissions using frontier or local model providers.
- Generate student-level feedback and score explanations.
- Store grading outputs for later review and comparison.
- Compare AI grades against a human gold standard.
- Measure error, bias, and agreement using evaluation metrics.
- Apply calibration to reduce systematic grading bias.
- Run a synthetic demo without exposing real student data.

---

## Local Setup

### 1. Clone The Repository

```bash
git clone https://github.com/raaaulnaidu/Bullseye.git
cd Bullseye
```

### 2. Create A Python Environment

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure API Keys

```bash
cp .env.example .env
```

Edit `.env` and add at least one model provider key:

```bash
ANTHROPIC_API_KEY=your_key_here
```

Optional providers:

```bash
OPENAI_API_KEY=your_key_here
HF_TOKEN=your_key_here
```

### 5. Run The App

```bash
streamlit run app.py
```

Then open:

```text
http://localhost:8501
```

If that port is already in use:

```bash
streamlit run app.py --server.port 8502
```

---

## Demo Without Real Student Data

Real course submissions are excluded from the repository for privacy and compliance reasons. A safe synthetic demo dataset can be generated with:

```bash
python create_demo_data.py
```

Then use the app to upload:

| Input Type | Demo File |
|---|---|
| Assignment instructions | `demo_data/assignment_instructions.docx` |
| Grading rubric | `demo_data/grading_rubric.docx` |
| Student submissions | files in `demo_data/student_submissions/` |

This allows a collaborator to test the full grading workflow without accessing real student work.

---

## Privacy And Data Handling

The project is designed around a privacy-first grading workflow.

The following files and folders are intentionally excluded from git:

- `.env`
- `lab01_data/`
- `submissions/`
- `ui_output/`
- `demo_data/`

The application includes a local anonymization step that removes common personally identifiable information before cloud model calls, including:

- Student names
- Email addresses
- Student IDs
- Phone numbers
- Course codes

Real student data should only be exchanged through approved institutional channels.

---

## Current Lab 01 Results

The current evaluated dataset contains 15 Lab 01 submissions.

| Metric | Current Result |
|---|---:|
| Students evaluated | 15 |
| Raw AI mean absolute error | 3.6 points |
| Raw AI bias | -3.6 points |
| Quadratic weighted kappa | 0.693 |
| Calibration offset | +3.86 points |
| Leave-one-out calibrated MAE | 1.253 points |
| Non-submission detection | 1/1 correctly scored as 0 |

Interpretation:

- The raw AI grader is consistently stricter than the human TA.
- Calibration reduces grading error substantially.
- The agreement score is promising, but the small sample size and low grade variance limit the strength of the conclusion.
- The system correctly identifies a non-submission case, which is important for real grading workflows.

Reproduce the main evaluation:

```bash
python evaluator.py \
  --human lab01_data/output/gold_standard_template.csv \
  --ai lab01_data/experiments/set2_results.json \
  --output lab01_data/output/evaluation_report.txt
```

Run calibration validation:

```bash
python calibration_experiment.py \
  --ai lab01_data/experiments/set2_results.json \
  --human lab01_data/output/gold_standard_template.csv
```

---

## Publication Direction

Recommended working title:

**Toward Privacy-Aware, Rubric-Calibrated AI Grading for University Assignments**

Recommended thesis:

> AI grading systems should not be evaluated only by whether they can generate plausible feedback. They should be evaluated as complete grading workflows that include privacy protection, rubric grounding, human review, measurable agreement with instructors, and calibration against systematic model bias.

This positions BullsEye as more than a single grading prompt. It is a full workflow for evaluating how LLM-based grading can support teaching assistant labor while preserving human oversight.

---

## Literature Positioning

The most relevant publication direction is to compare BullsEye against recent work on LLM-based assignment grading, short-answer grading, essay scoring, and retrieval-augmented educational assessment.

Useful literature anchors:

| Research Area | Relevance To BullsEye |
|---|---|
| LLM assignment grading | Establishes that LLMs can grade structured assignments, but often focuses on single-prompt grading. |
| Rubric-based grading | Supports the need for criterion-level evaluation and transparent score justification. |
| Retrieval-augmented grading | Motivates using assignment and rubric context instead of grading from submission text alone. |
| AI-human agreement metrics | Provides comparison points for MAE, bias, and quadratic weighted kappa. |
| Agentic AI workflows | Frames BullsEye as a multi-step grading assistant rather than a one-shot chatbot. |
| Privacy-aware education technology | Supports the need for anonymization and careful data handling in student-facing AI systems. |

---

## Gap-To-Experiment Map

| Literature Gap | BullsEye Response | Current Status |
|---|---|---|
| Many AI grading studies rely on single-shot prompts. | BullsEye uses a multi-step workflow: parsing, anonymization, grading, feedback, review, and evaluation. | Implemented |
| Privacy is often discussed but not built into the grading pipeline. | Local anonymization is applied before cloud model calls. | Implemented |
| Model grading bias is often reported but not corrected. | BullsEye measures bias and applies calibration against human grades. | Validated on Lab 01 |
| Few studies compare raw grading with calibrated grading. | The current experiment reports both raw MAE and leave-one-out calibrated MAE. | Implemented |
| Frontier/local model tradeoffs remain unclear. | The codebase supports hosted and local model comparison. | Needs full experiment |
| Retrieval quality can affect grading consistency. | Semantic RAG and evidence-aware grading are planned for the next experiment. | Next step |
| Many studies use larger samples than the current project. | The current dataset is a pilot; larger course datasets are needed. | Future work |

---

## Recommended Immediate Plan

1. Use the current Lab 01 results as a pilot study.
2. Run the same submissions across at least two model providers for model comparison.
3. Run the semantic RAG experiment and compare it against the current baseline.
4. Expand the dataset beyond 15 submissions to improve grade variance and statistical confidence.
5. Convert the current results into a short paper outline with the following structure:

```text
Introduction
Related Work
System Design
Experimental Setup
Results
Discussion
Limitations
Future Work
```

---

## Repository Files To Review

| File | Purpose |
|---|---|
| `README.md` | Main project overview and quickstart |
| `SETUP.md` | Detailed installation and troubleshooting guide |
| `docs/README.md` | Documentation index |
| `docs/FACULTY_SETUP_AND_PUBLICATION_BRIEF.md` | This shareable setup and research brief |
| `docs/PAPER_COMPARISON_SIMPLE.md` | Plain-language paper comparison for meetings |
| `docs/PUBLICATION_GAP_ANALYSIS.md` | Detailed literature gap analysis |
| `docs/RESULTS_LAB01.md` | Current Lab 01 evaluation results |
| `app.py` | Streamlit user interface |
| `calibrated_grader.py` | Main grading engine |
| `evaluator.py` | Evaluation metrics |
| `calibration_experiment.py` | Calibration validation |
| `create_demo_data.py` | Synthetic demo data generator |

---

## Decisions Needed

The next meeting can focus on four decisions:

1. Which publication venue should the first paper target?
2. Which paper should be used as the primary methodological comparison?
3. Should the next experiment prioritize semantic RAG, model comparison, or dataset expansion?
4. What data-sharing and privacy process should be used for the larger evaluation?

---

## Closing Summary

BullsEye is ready for collaborator setup and demonstration. The strongest current finding is that calibration reduces grading error from **3.6 points MAE** to **1.253 points MAE** on the Lab 01 pilot dataset. The most promising publication angle is a privacy-aware, rubric-calibrated AI grading workflow that evaluates not only model output quality, but also bias, calibration, human review, and practical deployment constraints.
