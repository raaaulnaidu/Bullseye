# AI Grading Assistant — TA User Guide

**Course:** CAI 3801 / ISM 6145 — AI for Analytics  
**Model:** Claude Sonnet 4.6 (frontier) or Qwen2.5 (local, free)

---

## Before You Start (One-time Setup)

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Add your API key**  
Create a file named `.env` in the project folder and add:
```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
```
Get your key at: [console.anthropic.com](https://console.anthropic.com)

**3. Verify it works**
```bash
python calibrated_grader.py --help
```

---

## Grading a New Assignment

### Step 1 — Prepare your files

Collect all student submissions into one folder:
```
submissions/
  John_Smith.pdf
  Jane_Doe.docx
  Alex_Brown.pdf
  ...
```
Submissions can be PDF or Word documents. File names become the student identifiers.

### Step 2 — Run the grader

**Option A — Simple interactive mode** *(recommended for first-time users)*
```bash
python calibrated_grader.py
```
It will ask you for each file path one at a time. You can drag-and-drop files into the terminal to fill the path automatically.

**Option B — Command line** *(faster once you know the paths)*
```bash
python calibrated_grader.py \
  --instructions  "path/to/assignment_instructions.pdf" \
  --rubric        "path/to/rubric.pdf" \
  --submissions   "path/to/submissions/" \
  --output        "path/to/output/" \
  --assignment    "CAI 3801 Lab 02"
```

### Step 3 — Review results

Open the visual dashboard:
```bash
python dashboard.py --input path/to/output/all_results.json
```

This shows each student's score, criterion breakdown, and feedback. Spot-check 3–5 students to confirm the grading looks reasonable before releasing grades.

---

## Output Files

After grading, the output folder contains:

| File | What it is |
|---|---|
| `all_results.json` | All scores and feedback in structured format |
| `Student_001.json` | Individual result per student |
| `gold_standard_template.csv` | Fill this in with your human scores for accuracy evaluation |

---

## Evaluating Accuracy (Optional but Recommended)

To measure how closely the AI matches human grading:

**1.** Open `gold_standard_template.csv` and fill in your scores for each student.

**2.** Run the evaluator:
```bash
python evaluator.py \
  --human path/to/output/gold_standard_template.csv \
  --ai    path/to/output/all_results.json
```

**3.** You will see:
- **MAE** — average point difference between AI and human
- **Agreement %** — how often they match within ±2 points
- **QWK** — Quadratic Weighted Kappa (published benchmark: 0.68)

---

## Adjusting for Your Assignment

### Calibration offset
The grader applies a +3.5 point offset by default to match observed human TA generosity. Adjust with:
```bash
python calibrated_grader.py --offset 2.0 ...
```
- Increase if AI grades feel too low
- Decrease if AI grades feel too high
- Set to `0` to use raw AI scores

### Using a pre-defined criteria file
If you already have the rubric criteria saved (e.g. from a previous run), skip the parsing step:
```bash
python calibrated_grader.py --criteria lab01_data/source_files/lab01_criteria.json ...
```

---

## Using the Free Local Model (No API Cost)

If you don't have API credits, you can grade for free using a local model.

**1.** Install Ollama: [ollama.com](https://ollama.com)

**2.** Pull a lightweight model:
```bash
ollama pull qwen2.5:3b
```

**3.** Start Ollama (keep this terminal open):
```bash
ollama serve
```

**4.** Run the grader with `--provider ollama`:
```bash
python calibrated_grader.py \
  --provider  ollama \
  --model     qwen2.5:3b \
  --criteria  path/to/criteria.json \
  --submissions path/to/submissions/ \
  --output    path/to/output/
```

> **Note:** Local models are less consistent than Claude. Always spot-check results before releasing grades.

---

## Comparing Two Models

To generate a side-by-side comparison report (useful for professor demos):
```bash
python model_comparison.py \
  --frontier  path/to/frontier_results/all_results.json \
  --local     path/to/local_results/all_results.json \
  --output    path/to/comparison/
```
Opens as an HTML file — share it with your professor directly.

---

## Privacy and FERPA

- Student names and IDs are **stripped locally** before any text is sent to Claude
- The API only ever receives anonymized content
- With `--provider ollama`, **nothing leaves your machine at all**

---

## Quick Reference

| Task | Command |
|---|---|
| Grade an assignment | `python calibrated_grader.py` |
| View dashboard | `python dashboard.py --input output/all_results.json` |
| Evaluate accuracy | `python evaluator.py --human scores.csv --ai output/all_results.json` |
| Compare two models | `python model_comparison.py --frontier f.json --local l.json` |
| Grade for free (local) | Add `--provider ollama --model qwen2.5:3b` |

---

## Estimated Cost (Claude Sonnet 4.6)

| Class size | Cost per assignment |
|---|---|
| 15 students | ~$0.45 |
| 30 students | ~$0.90 |
| 100 students | ~$3.00 (50% discount via Batch API) |

---

## Getting Help

Contact: swethasingireddy8@gmail.com  
Project repo: `/Users/rahulnaidu/Desktop/ta_grader/`
