# BullsEye Setup Guide

This guide is for running BullsEye locally from a fresh clone.

## 1. Clone And Install

```bash
git clone https://github.com/raaaulnaidu/Bullseye.git
cd Bullseye

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

## 2. Configure API Keys

```bash
cp .env.example .env
```

Edit `.env`.

Recommended:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Optional:

```bash
OPENAI_API_KEY=sk-proj-...
HF_TOKEN=hf_...
```

For fully local grading with Ollama, no API key is needed, but Ollama must be running separately.

## 3. Start The App

```bash
streamlit run app.py
```

Open the local URL printed by Streamlit, usually:

```text
http://localhost:8501
```

## 4. Run With Demo Data

Generate synthetic data:

```bash
python create_demo_data.py
```

In the app, upload:

- Instructions: `demo_data/assignment_instructions.docx`
- Rubric: `demo_data/grading_rubric.docx`
- Submissions: files inside `demo_data/student_submissions/`

## 5. Run Existing Lab 01 Evaluation

The real Lab 01 data is FERPA-sensitive and ignored by git. If you receive it through an approved channel, place it under `lab01_data/`.

Then run:

```bash
python evaluator.py \
  --human lab01_data/output/gold_standard_template.csv \
  --ai lab01_data/experiments/set2_results.json \
  --output lab01_data/output/evaluation_report.txt
```

Calibration validation:

```bash
python calibration_experiment.py \
  --ai lab01_data/experiments/set2_results.json \
  --human lab01_data/output/gold_standard_template.csv
```

## 6. Publication Experiment Runner

Semantic RAG comparison:

```bash
python run_experiments.py --run set5 --anthropic-key "$ANTHROPIC_API_KEY"
```

Hosted Hugging Face comparison:

```bash
python run_experiments.py --run hf --hf-token "$HF_TOKEN"
```

Few-shot example rebuild:

```bash
python run_experiments.py --run shots
```

## 7. Docker

```bash
docker build -t bullseye-grader .
docker run --rm -p 8501:8501 --env-file .env bullseye-grader
```

Open:

```text
http://localhost:8501
```

## 8. Privacy

Do not commit:

- `.env`
- real student submissions
- `lab01_data/`
- `submissions/`
- `ui_output/`

These are ignored by git and Docker.
