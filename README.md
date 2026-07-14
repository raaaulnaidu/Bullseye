# BullsEye — AI Grading Assistant

BullsEye is a privacy-aware, rubric-calibrated AI grading assistant for university TA workflows. It reads assignment instructions, rubrics, and student submissions; anonymizes PII locally; grades with frontier or local models; stores feedback; and evaluates AI grades against a human gold standard.

## What It Does

- Upload assignment instructions, rubric, and submissions through a Streamlit UI.
- Grade with Claude, OpenAI, Hugging Face, or local Ollama models.
- Strip names, emails, IDs, phone numbers, and course codes before model calls.
- Review/edit all student scores and feedback in a human-in-the-loop queue.
- Compare models by score, feedback, cost, and saved model inputs.
- Evaluate against human grades with MAE, RMSE, bias, Pearson r, Cohen's kappa, and QWK.
- Save run artifacts for research reproducibility.

## Repository Structure

```text
.
├── app.py                         # Main Streamlit application
├── calibrated_grader.py           # Privacy/RAG/model grading engine
├── document_reader.py             # Submission parsing
├── privacy_processor.py           # Local PII anonymization
├── rag_retriever.py               # Evidence retrieval
├── evaluator.py                   # AI-vs-human metrics
├── calibration_experiment.py      # Bias calibration validation
├── run_experiments.py             # Publication experiment runner
├── create_demo_data.py            # Synthetic demo data generator
├── docs/                          # Faculty-facing docs and research notes
├── src/streamlit_app.py           # Compatibility entrypoint
├── SETUP.md                       # Detailed setup guide
└── requirements.txt               # Python dependencies
```

## Quick Start For Faculty

```bash
git clone <repo-url> ta_grader
cd ta_grader

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add at least one API key:

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
HF_TOKEN=hf_...
```

Start the app:

```bash
streamlit run app.py
```

Open the URL Streamlit prints, usually:

```text
http://localhost:8501
```

## Demo Without Student Data

Generate synthetic demo files:

```bash
python create_demo_data.py
```

Then in the app:

- Assignment instructions: `demo_data/assignment_instructions.docx`
- Grading rubric: `demo_data/grading_rubric.docx`
- Student submissions: upload the files in `demo_data/student_submissions/`

The demo files contain no real student data.

## Documentation

Faculty-facing and research materials are organized under [`docs/`](docs/):

| Document | Purpose |
|---|---|
| [`docs/FACULTY_SETUP_AND_PUBLICATION_BRIEF.md`](docs/FACULTY_SETUP_AND_PUBLICATION_BRIEF.md) | Shareable setup and publication brief |
| [`docs/PAPER_COMPARISON_SIMPLE.md`](docs/PAPER_COMPARISON_SIMPLE.md) | Simple explanation of related papers and how BullsEye differs |
| [`docs/RESULTS_LAB01.md`](docs/RESULTS_LAB01.md) | Current Lab 01 empirical results |
| [`docs/PUBLICATION_GAP_ANALYSIS.md`](docs/PUBLICATION_GAP_ANALYSIS.md) | Gap-to-experiment publication map |
| [`docs/README.md`](docs/README.md) | Documentation index |

## Current Research Results

Reproduce the current evaluation:

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

Note: `lab01_data/` is FERPA-sensitive and intentionally ignored by git. Share real course data only through approved institutional channels.

## Publication Track

The immediate publication angle is:

> Agentic, privacy-preserving AI grading with rubric calibration, human review, and measured AI-human agreement.

Core evidence so far:

- Full 15/15 Lab 01 human gold-standard comparison.
- AI negative bias: about `-3.6` points.
- QWK: about `0.693` on the full set, leverage-sensitive due to one non-submission.
- Calibration offset: about `+3.86` points.
- LOOCV-calibrated MAE improves from `3.6` to about `1.25`.
- One non-submission was correctly identified and scored `0/20`.

## Main Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI |
| `calibrated_grader.py` | Main privacy/RAG/model grading engine |
| `document_reader.py` | PDF, DOCX, TXT, Tableau TWB/TWBX extraction |
| `privacy_processor.py` | Local PII anonymization |
| `rag_retriever.py` | Keyword and semantic evidence retrieval |
| `evaluator.py` | AI-vs-human metrics |
| `calibration_experiment.py` | Raw vs calibrated LOOCV validation |
| `run_experiments.py` | Publication experiment runner |
| `docs/` | Faculty-facing documentation, results, and publication notes |

## Privacy Notes

- `.env`, `lab01_data/`, `submissions/`, and `ui_output/` are ignored by git.
- Do not commit real student submissions, API keys, or generated grading outputs containing student work.
- For demos, use `create_demo_data.py`.

## Docker

Build and run:

```bash
docker build -t bullseye-grader .
docker run --rm -p 8501:8501 --env-file .env bullseye-grader
```

Then open:

```text
http://localhost:8501
```
