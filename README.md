---
title: BullsEye
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.50.0
app_file: app.py
pinned: false
license: mit
---

# AI Grading Assistant
### Automated feedback and grading for Teaching Assistants — AI for Analytics Course

> **HF Spaces secrets:** Set `ANTHROPIC_API_KEY` and `HF_TOKEN` in Space Settings → Variables and Secrets.

---

## What It Does

This tool reads your assignment instructions, grading rubric, and a folder of student submissions, then uses Claude AI to automatically produce:

- **Personalised feedback** for every student (`.txt` files ready to send)
- **CSV grade sheet** with scores per rubric criterion across the whole class
- **HTML dashboard** — open in any browser to review all grades at a glance

Supported file formats: `.pdf` and `.docx` for all inputs.

---

## Folder Structure

```
ta_grader/
├── main.py                  ← Run this to start grading
├── grader.py                ← Claude AI grading engine
├── document_reader.py       ← PDF + DOCX text extraction
├── report_generator.py      ← Generates feedback, CSV, and HTML
├── mock_test.py             ← Test the full pipeline for free (no API key)
├── create_sample_data.py    ← Generates 3 sample student submissions
├── requirements.txt         ← Python dependencies
├── .env.example             ← Copy this to .env and add your API key
└── sample_data/             ← Created by create_sample_data.py
```

---

## Setup (One Time Only)

### 1. Install Python
Download from [python.org](https://python.org/downloads) — version 3.9 or newer.

### 2. Install dependencies
Open a terminal inside the `ta_grader/` folder and run:
```
pip install anthropic pdfplumber python-docx rich
```

### 3. Add your API key
- Get a free key at [console.anthropic.com](https://console.anthropic.com) — new accounts get $5 free credit
- Inside `ta_grader/`, find `.env.example` and rename it to `.env`
- Open `.env` and replace `sk-ant-...` with your real key:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```
Save the file. The app picks it up automatically every run.

---

## How to Run

### Option A — Interactive (recommended)
```
python main.py
```
The app walks you through everything step by step.

### Option B — Command line
```
python main.py \
    --instructions path/to/instructions.pdf \
    --rubric       path/to/rubric.docx \
    --submissions  path/to/students_folder/ \
    --output       path/to/output_folder/ \
    --assignment   "Assignment 1: EDA with Python"
```

### Test without spending money
```
python create_sample_data.py    # creates 3 fake student files
python mock_test.py             # runs full pipeline with no API call
```
Check `sample_data/grading_output/` — open the `.html` file in your browser to see what the real output looks like.

---

## Output Files

After grading, you'll find three things in your output folder:

| File | What it is |
|---|---|
| `grading_report_[date].html` | Visual dashboard — open in browser, click each student to expand |
| `grading_summary_[date].csv` | Full class spreadsheet — import into your grade book |
| `student_feedback/[name]_feedback.txt` | One file per student — ready to paste into feedback emails |

---

## Controlling Cost

The model is set in `grader.py` on line 56. Change it to control cost vs quality:

```python
# Best value — recommended for most assignments
model: str = "claude-sonnet-4-6",

# Budget mode — good for large classes or quick first-pass
model: str = "claude-haiku-4-5-20251001",

# Highest quality — use only when maximum detail matters
model: str = "claude-opus-4-6",
```

| Model | Cost per 30 students | Quality for grading |
|---|---|---|
| Sonnet (recommended) | ~$0.85 | Excellent |
| Haiku (budget) | ~$0.22 | Good |
| Opus | ~$4.30 | Excellent |

---

## Tips for Best Results

- **Name student files clearly** — `firstname_lastname.docx` gives the cleanest name extraction
- **Write a detailed rubric** — include what full marks, partial credit, and zero looks like per criterion
- **Always review before sending** — AI grades are a first pass; adjust anything you disagree with
- **Use text-based PDFs** — scanned/handwritten PDFs cannot be read; ask students to submit typed documents

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: pdfplumber` | `pip install pdfplumber` |
| `ModuleNotFoundError: docx` | `pip install python-docx` |
| `AuthenticationError` | Check `.env` file has the correct key starting with `sk-ant-` |
| Student name looks garbled | Rename file to `firstname_lastname.docx` format |
| PDF shows empty text | PDF is image-based — convert to text PDF from the source app |

---

## Files Needed Each Run

You need three things pointing to your actual assignment:

1. **Instructions file** — the assignment brief (PDF or DOCX)
2. **Rubric file** — grading criteria with point values (PDF or DOCX)
3. **Submissions folder** — a folder containing one file per student (PDF or DOCX)

For every new assignment, just run `python main.py` and point it at different files — no code changes needed.
