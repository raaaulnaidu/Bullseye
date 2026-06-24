---
title: BullsEye
emoji: 🎯
colorFrom: green
colorTo: green
sdk: streamlit
sdk_version: 1.50.0
app_file: app.py
pinned: false
license: mit
---

# 🎯 BullsEye — AI Grading Assistant

AI-powered grading tool for Teaching Assistants at the University of South Florida.

**Courses:** AI for Analytics · Business Statistics

## Features
- Upload instructions, rubric, and student submissions (PDF, DOCX, or ZIP)
- Grade with GPT, Claude, Hugging Face (free), or Ollama (local)
- Edit grades and feedback directly in the UI
- Download results as JSON or CSV
- FERPA-compliant — student names stripped before any API call

## Setup
Set these in Space **Settings → Variables and Secrets**:
- `OPENAI_API_KEY` — your OpenAI key
- `HF_TOKEN` — your Hugging Face token (optional)
