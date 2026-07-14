# BullsEye Paper Comparison: Simple Meeting Notes

## Short Answer

Most published papers show that LLMs can grade student work reasonably well when they are given a rubric, examples, or retrieved course context. However, most treat grading as a single model call: give the model the question, rubric, and answer, then ask for a score.

BullsEye is different because it is built as a complete grading workflow:

```text
read files -> anonymize student data -> retrieve evidence -> grade -> explain -> store feedback -> compare with human grades -> calibrate bias -> flag for review
```

So the contribution is not only "Can AI grade?" The contribution is:

> Can we build a privacy-aware, human-in-the-loop, rubric-calibrated AI grading assistant that can be evaluated against human TA grading and improved through calibration?

---

## What Each Paper Is Doing

| Paper / Area | What The Paper Is Doing In Simple Language | Main Finding | What It Does Not Fully Address |
|---|---|---|---|
| **The Shift to Agentic AI: Evidence from Codex** | Studies how people are starting to use AI tools that can take actions, run workflows, and complete bigger tasks, instead of only answering questions. | Agentic AI use is growing quickly and changing work patterns. | It is not about education or grading accuracy. It helps frame why an agentic grading assistant matters now. |
| **Automated Assignment Grading with LLMs: Bioinformatics Course** | Uses LLMs to grade real student assignments using a rubric and example answers. Compares AI grades to human TA grades. | LLM grading can be close to human grading when the prompt is well-designed. | It is mostly a grading accuracy study, not a privacy-aware or agentic workflow. |
| **RAG for Short-Answer Grading** | Gives the model extra retrieved course/context information before grading short answers. | Semantic RAG improves agreement with human graders compared with basic prompting. | It focuses on retrieval accuracy, but not full grading workflow, privacy, or calibration. |
| **ChatGPT vs Claude Essay Scoring** | Compares ChatGPT and Claude on essay grading against human raters. | Both models can grade, but they tend to be stricter than humans. Claude performs strongly in some settings. | It identifies bias, but does not build a calibration workflow to correct it. |
| **LLM Essay Grading With QWK Benchmark** | Tests different LLMs for essay scoring and reports agreement using quadratic weighted kappa. | Detailed rubrics improve agreement; reported benchmark is around QWK 0.68. | It mainly reports agreement metrics, not privacy, feedback storage, or human review workflow. |
| **Open-Ended GenAI Grading in Higher Education** | Tests stronger models such as GPT-o1 on many open-ended student responses. | Very strong models can approach human agreement, but cost can be high. | It does not fully solve cost, privacy, or local-model tradeoffs. |
| **LLM Assessment RAG for Higher Education** | Builds a RAG-based grading system using a curated course knowledge base. | Course-specific RAG performs better than generic LLM grading. | It is closest to BullsEye architecturally, but does not emphasize local PII anonymization and calibration against instructor bias. |

---

## How BullsEye Is Different

| Dimension | Most Existing Papers | BullsEye |
|---|---|---|
| Grading method | Single prompt or single LLM call | Multi-step grading workflow |
| Privacy | Usually discussed as a concern | Built into the pipeline through local anonymization |
| Human comparison | Often compares AI score to human score | Compares AI to human gold standard and measures bias |
| Bias handling | Reports disagreement or strictness | Applies calibration to reduce systematic under-scoring |
| Feedback storage | Often not a product feature | Stores student feedback for review and model comparison |
| Human review | Usually outside the system | Designed for human-in-the-loop review |
| Model comparison | Some compare models | BullsEye can compare frontier, hosted, and local models |
| RAG | Some papers use semantic RAG | BullsEye currently has keyword RAG and is moving toward semantic RAG |
| Practical deployment | Mostly research experiments | Built as a runnable Streamlit app for real TA workflow |

---

## Strongest Current Research Finding

The strongest current finding is not just that the AI can grade. The stronger finding is:

> The AI grader systematically under-scores compared with the human TA, but calibration reduces the error substantially.

Current Lab 01 result:

| Metric | Result |
|---|---:|
| Students evaluated | 15 |
| Raw AI MAE | 3.6 points |
| AI bias | -3.6 points |
| QWK | 0.693 |
| Calibration offset | +3.86 points |
| LOOCV calibrated MAE | 1.253 points |

Simple explanation:

> The model understood the rubric and gave specific feedback, but it graded more strictly than the human TA. After learning the instructor's grading style through a calibration offset, the average grading error dropped from 3.6 points to about 1.25 points.

That is a strong publication angle because it moves from AI grading to AI grading alignment with a real instructor.

---

## Main Gap BullsEye Addresses

The literature already shows that AI can grade. The gap is that most papers do not combine all of these together:

- Privacy protection before model calls
- Rubric-based grading
- Evidence retrieval
- Human review
- Feedback storage
- AI-human comparison
- Bias measurement
- Calibration
- Model comparison
- A runnable app workflow

BullsEye combines these into one system.

Clean gap statement:

> Existing AI grading research mainly evaluates whether LLMs can produce scores similar to human graders. BullsEye studies a broader question: how to build and evaluate a privacy-aware, human-in-the-loop grading workflow that can detect model bias, calibrate to instructor grading style, and support real teaching assistant workflows.

---

## What Still Needs Improvement

| Current Limitation | Why It Matters | Next Step |
|---|---|---|
| Small dataset: 15 submissions | Good for pilot results, but weak for publication-level claims | Run on a larger class dataset, ideally 100+ submissions |
| Low grade variance | Most students scored high, so ranking metrics are less reliable | Include assignments with broader grade spread |
| Keyword RAG underperformed | Keyword retrieval can miss relevant evidence | Run semantic RAG and compare against current baseline |
| Few-shot experiment failed | High-only examples made the model too harsh or unstable | Rebuild few-shot examples using high, medium, and low samples |
| Model comparison incomplete | Need evidence for Claude vs OpenAI vs local models | Run the same assignment through multiple models |
| Time savings not measured yet | Important for the agentic/workforce argument | Log grading time per submission and estimate TA hours saved |

---

## Simple Meeting Script

Here is the version to say out loud:

> I reviewed the related papers, and most of them are asking whether LLMs can grade student work accurately when given a rubric, examples, or retrieved course context. They show that LLM grading can be close to human grading, but they usually treat grading as one model call.
>
> My project is different because BullsEye is a full grading workflow, not just a prompt. It reads assignment files, anonymizes student information, grades with a rubric, generates feedback, stores the results, compares AI grades against a human gold standard, and applies calibration when the model is systematically stricter than the instructor.
>
> The strongest current result is that the AI under-scored by about 3.6 points on average, but after calibration the error dropped to about 1.25 points using leave-one-out validation. That means the model was not randomly wrong; it had a consistent grading bias that we can measure and correct.
>
> The main gap I think we can target is privacy-aware, rubric-calibrated, human-in-the-loop AI grading. The next experiments should be semantic RAG, model comparison, and a larger dataset so we can make the publication stronger.

---

## One-Sentence Contribution

> BullsEye contributes a privacy-aware, rubric-calibrated AI grading workflow that measures and corrects model grading bias while supporting human review and practical TA deployment.
