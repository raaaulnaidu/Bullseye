"""
app.py — BullsEye  (Streamlit UI — USF Theme)
Run:  streamlit run app.py
"""

import json, os, shutil, tempfile, time, zipfile, csv, io
from pathlib import Path
from collections import Counter
from datetime import datetime
import streamlit as st

st.set_page_config(
    page_title="BullsEye · USF Grader",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
#MainMenu, footer { visibility: hidden; }

/* Sidebar — USF dark green */
section[data-testid="stSidebar"] {
    background: #003d2a;
    min-width: 230px;
}
section[data-testid="stSidebar"] * { color: #d4ede2 !important; }
section[data-testid="stSidebar"] hr { border-color: #1a5c3f !important; }
section[data-testid="stSidebar"] .stRadio label { color: #a8d4bc !important; font-size: 0.9rem !important; }
section[data-testid="stSidebar"] .stRadio [data-baseweb="radio"] svg { fill: #CFC493 !important; }

/* Primary button */
div.stButton > button[kind="primary"] {
    background: #006747; color: white; border: none;
    border-radius: 8px; padding: 0.55rem 2rem;
    font-weight: 700; font-size: 0.95rem;
}
div.stButton > button[kind="primary"]:hover   { background: #004d35; }
div.stButton > button[kind="primary"]:disabled { background: #b0cec0; }

/* Secondary button */
div.stButton > button:not([kind="primary"]) {
    border: 1.5px solid #006747; color: #006747;
    border-radius: 8px; font-weight: 600;
}

/* Progress bar */
div[data-testid="stProgressBar"] > div > div { background: #006747; }

/* Tabs */
.stTabs [aria-selected="true"] {
    color: #006747 !important;
    border-bottom: 3px solid #006747 !important;
}
.stTabs [data-baseweb="tab"] { font-weight: 600; }

/* Metric */
div[data-testid="stMetricValue"] { color: #006747; font-weight: 800; }

/* Feedback boxes */
div[data-testid="stTextArea"] textarea {
    border: 1.5px solid #c8dfd4;
    border-radius: 8px;
    background: #f8fbf9;
    font-size: 0.88rem;
}
div[data-testid="stTextArea"] textarea:focus {
    border-color: #006747;
    box-shadow: 0 0 0 2px rgba(0,103,71,0.12);
}

/* Score input */
div[data-testid="stNumberInput"] input {
    border: 1.5px solid #c8dfd4 !important;
    border-radius: 8px !important;
    text-align: center !important;
    font-weight: 700 !important;
    color: #006747 !important;
}

div[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #d9e7df;
    border-radius: 8px;
    padding: 0.75rem 0.9rem;
}

.bullseye-workspace {
    border: 1px solid #d9e7df;
    border-left: 5px solid #006747;
    background: #f8fbf9;
    border-radius: 8px;
    padding: 1rem 1.1rem;
    margin-bottom: 1rem;
}

.bullseye-workspace strong { color: #004d35; }

.small-muted {
    color: #5f756c;
    font-size: 0.86rem;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar navigation ────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='padding:0.5rem 0 1rem'>
      <div style='font-size:1.25rem;font-weight:800;color:#CFC493;'>🎯 BullsEye</div>
      <div style='font-size:0.75rem;color:#7aad91;margin-top:0.2rem;'>University of South Florida</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("**Courses**")
    st.caption("AI for Analytics")
    st.caption("Business Statistics")

    st.divider()

    st.markdown("**Navigation**")
    nav = st.radio("Navigation", [
        "Grade Submissions", "Review Queue", "Class Analytics",
        "Rubric Library", "Model Comparison", "Evaluate & Publish"
    ],
                   label_visibility="collapsed")

    st.divider()
    st.markdown("**Quick Tips**")
    st.caption("• Upload a criteria JSON to skip rubric parsing")
    st.caption("• ZIP multiple submissions into one file")
    st.caption("• Review Queue is fastest for approvals")
    st.caption("• Analytics shows class-wide gaps")
    st.caption("• Rubric Library reuses prior criteria")

# ── Load .env ────────────────────────────────────────────────────
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ[k.strip()] = v.strip()

# ── Helpers ──────────────────────────────────────────────────────
def save_upload(f, dest):
    p = dest / f.name; p.write_bytes(f.getbuffer()); return p

def extract_submissions(upload, dest):
    saved = save_upload(upload, dest)
    if saved.suffix.lower() == ".zip":
        ex = dest / "extracted"; ex.mkdir(exist_ok=True)
        with zipfile.ZipFile(saved) as z: z.extractall(ex)
        return sorted(p for p in ex.rglob("*")
                      if p.is_file()
                      and p.suffix.lower() in {".pdf",".docx",".txt",".twb",".twbx"}
                      and not p.name.startswith((".", "__")))
    return [saved]

def letter_grade(pct):
    for t, g in [(93,"A"),(90,"A-"),(87,"B+"),(83,"B"),(80,"B-"),
                 (77,"C+"),(73,"C"),(70,"C-"),(60,"D")]:
        if pct >= t: return g
    return "F"

GRADE_COLOR = {"A":"🟢","A-":"🟢","B+":"🔵","B":"🔵","B-":"🔵",
               "C+":"🟡","C":"🟡","C-":"🟡","D":"🟠","F":"🔴"}

def safe_assignment_slug(name):
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", " ") else "-" for ch in name.strip())
    return cleaned.replace(" ", "_") or "assignment"

def feedback_records(results, run_id="", provider="", model="", rag_mode=""):
    rows = []
    for r in results:
        grade = r.get("letter_grade") or letter_grade(r.get("percentage", 0))
        base = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "assignment": r.get("assignment_name", ""),
            "student_id": r.get("student_id", ""),
            "provider": provider or r.get("model_trace", {}).get("provider", ""),
            "model": model or r.get("model_trace", {}).get("model", ""),
            "rag_mode": rag_mode or r.get("model_trace", {}).get("rag_mode", ""),
            "evidence_mode": r.get("model_trace", {}).get("evidence_mode", ""),
            "total_score": r.get("total_score", 0),
            "max_score": r.get("max_score", 0),
            "percentage": r.get("percentage", 0),
            "letter_grade": grade,
            "confidence_score": r.get("confidence_score", ""),
            "review_flags": "; ".join(r.get("review_flags", [])),
            "overall_feedback": r.get("overall_feedback", ""),
        }
        criteria = r.get("criteria", [])
        if not criteria:
            rows.append(base)
            continue
        for c in criteria:
            rows.append({
                **base,
                "criterion": c.get("name", ""),
                "criterion_score": c.get("awarded_points", ""),
                "criterion_max": c.get("max_points", ""),
                "completed": c.get("completed", ""),
                "missing_or_weak": c.get("missing_or_weak", ""),
                "suggestion": c.get("suggestion", ""),
            })
    return rows

def write_feedback_artifacts(output_dir, results, run_id, provider, model, rag_mode):
    records = feedback_records(results, run_id, provider, model, rag_mode)
    history_jsonl = output_dir / "feedback_history.jsonl"
    with history_jsonl.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    fieldnames = [
        "run_id", "timestamp", "assignment", "student_id", "provider", "model", "rag_mode", "evidence_mode",
        "total_score", "max_score", "percentage", "letter_grade", "confidence_score", "review_flags", "overall_feedback",
        "criterion", "criterion_score", "criterion_max", "completed", "missing_or_weak", "suggestion",
    ]
    history_csv = output_dir / "feedback_history.csv"
    write_header = not history_csv.exists()
    with history_csv.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(records)

    feedback_csv = output_dir / "feedback_log.csv"
    with feedback_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    return records, history_jsonl, history_csv, feedback_csv

RUBRIC_LIBRARY_DIR = Path("rubric_library")

def load_rubric_library():
    RUBRIC_LIBRARY_DIR.mkdir(exist_ok=True)
    items = {}
    for path in sorted(RUBRIC_LIBRARY_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            label = data.get("name") or path.stem
            items[label] = {"path": path, **data}
        except Exception:
            continue
    return items

def save_rubric_to_library(name, criteria, course="", outcomes=""):
    RUBRIC_LIBRARY_DIR.mkdir(exist_ok=True)
    slug = safe_assignment_slug(name)
    path = RUBRIC_LIBRARY_DIR / f"{slug}.json"
    payload = {
        "name": name,
        "course": course,
        "outcomes": outcomes,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "criteria": criteria,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path

def criteria_from_result(result):
    return result.get("rubric_criteria") or result.get("criteria", [])

def result_status(result, review_status):
    sid = result.get("student_id", "")
    if review_status.get(sid) == "approved":
        return "Approved"
    trace_note = result.get("consistency_notes", "")
    if result.get("review_flags") or result.get("confidence_score", 100) < 75:
        return "Needs Review"
    if "parse" in trace_note.lower() or result.get("percentage", 0) < 70:
        return "Needs Review"
    return "Ready"

def review_rows(results, review_status):
    rows = []
    for r in results:
        pct = r.get("percentage", 0)
        grade = r.get("letter_grade") or letter_grade(pct)
        weak = [
            c.get("name", "")
            for c in r.get("criteria", [])
            if float(c.get("awarded_points", 0)) < float(c.get("max_points", 1)) * 0.75
        ]
        rows.append({
            "Student": r.get("student_id", ""),
            "Status": result_status(r, review_status),
            "Score": r.get("total_score", 0),
            "Max": r.get("max_score", 0),
            "%": round(pct, 1),
            "Grade": grade,
            "Confidence": r.get("confidence_score", ""),
            "Flags": "; ".join(r.get("review_flags", [])[:2]),
            "Weak criteria": ", ".join(weak[:3]),
            "Feedback": r.get("overall_feedback", "")[:140],
        })
    return rows

def save_review_status(output_dir, review_status):
    if output_dir:
        Path(output_dir, "review_status.json").write_text(
            json.dumps(review_status, indent=2), encoding="utf-8"
        )

def load_review_status(output_dir):
    if output_dir:
        path = Path(output_dir, "review_status.json")
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
    return {}

SCORING_PRESETS = {
    "Lenient TA": {"pct_full": 95, "pct_good": 88, "pct_partial": 65, "pct_attempt": 25},
    "Balanced": {"pct_full": 98, "pct_good": 92, "pct_partial": 75, "pct_attempt": 35},
    "Strict rubric": {"pct_full": 100, "pct_good": 95, "pct_partial": 85, "pct_attempt": 45},
}

# ── Header ───────────────────────────────────────────────────────
st.markdown("""
<div style="background:linear-gradient(135deg,#006747,#004d35);
            padding:1.2rem 2rem;border-radius:10px;margin-bottom:1.5rem;">
  <span style="color:#CFC493;font-size:1.4rem;font-weight:800;">🎯 BullsEye</span><br>
  <span style="color:#a8c8b8;font-size:0.82rem;">
    AI for Analytics &nbsp;·&nbsp; Business Statistics &nbsp;·&nbsp; University of South Florida
  </span>
</div>
""", unsafe_allow_html=True)

# ── Tab routing from sidebar nav ──────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Grade Submissions", "Review Queue", "Class Analytics",
    "Rubric Library", "Model Comparison", "Evaluate & Publish"
])


# ═══════════════════════════════════════════════════
# TAB 1 — GRADE
# ═══════════════════════════════════════════════════
with tab1:
    st.subheader("Workflow")
    wf1, wf2, wf3, wf4 = st.columns(4)
    wf1.metric("1", "Upload")
    wf2.metric("2", "Preview")
    wf3.metric("3", "Grade")
    wf4.metric("4", "Review")
    st.caption("Built like a classroom grading workflow: upload files, inspect what the model will see, run grading, then approve or edit in the Review Queue.")
    st.divider()

    # ── Provider ────────────────────────────────────
    st.subheader("1 · Choose AI Provider")
    provider_choice = st.radio(
        "AI Provider", ["GPT (OpenAI)", "Claude (Anthropic)", "Hugging Face · Free", "Ollama · Local"],
        horizontal=True, label_visibility="collapsed",
    )
    provider_key = {
        "GPT (OpenAI)":        "openai",
        "Claude (Anthropic)":  "anthropic",
        "Hugging Face · Free": "huggingface",
        "Ollama · Local":      "ollama",
    }[provider_choice]

    col_m, col_k = st.columns(2)

    if provider_key == "openai":
        with col_m:
            model_name = st.selectbox("Model",
                ["gpt-4o-mini","gpt-4o","gpt-4-turbo","gpt-3.5-turbo"])
            st.caption("gpt-4o-mini is fast and cheap (~$0.01/student)")
        with col_k:
            api_key = st.text_input("OpenAI API Key", type="password",
                                    value=os.environ.get("OPENAI_API_KEY",""),
                                    placeholder="sk-proj-...")

    elif provider_key == "anthropic":
        with col_m:
            model_name = st.selectbox("Model",
                ["claude-sonnet-4-6","claude-haiku-4-5-20251001"])
        with col_k:
            api_key = st.text_input("Anthropic API Key", type="password",
                                    value=os.environ.get("ANTHROPIC_API_KEY",""),
                                    placeholder="sk-ant-...")

    elif provider_key == "huggingface":
        with col_m:
            model_name = st.selectbox("Model", [
                "Qwen/Qwen2.5-7B-Instruct",
                "mistralai/Mistral-7B-Instruct-v0.3",
                "meta-llama/Llama-3.1-8B-Instruct",
                "HuggingFaceH4/zephyr-7b-beta",
            ])
            st.caption("Runs on HF's GPU — your laptop stays cool")
        with col_k:
            api_key = st.text_input("Hugging Face Token", type="password",
                                    value=os.environ.get("HF_TOKEN",""),
                                    placeholder="hf_...")

    else:  # ollama
        with col_m:
            model_name = st.text_input("Ollama Model", value="qwen2.5:3b")
        with col_k:
            st.info("Run `ollama serve` in a terminal before clicking Grade.")
        api_key = None

    st.divider()

    # ── Assignment name ──────────────────────────────
    st.subheader("2 · Assignment Details")
    assignment_name = st.text_input("Assignment Name",
                                    placeholder="e.g. Assignment 1 — Data Analysis",
                                    value=st.session_state.get("assignment_name",""))
    meta1, meta2 = st.columns(2)
    with meta1:
        course_name = st.text_input("Course / Section", placeholder="e.g. CAI 3801 · Section 01")
    with meta2:
        learning_outcomes = st.text_input("Learning Outcomes", placeholder="e.g. LO1, LO3, Data storytelling")

    saved_rubrics = load_rubric_library()
    saved_rubric_choice = "None"
    if saved_rubrics:
        saved_rubric_choice = st.selectbox(
            "Use saved rubric criteria",
            ["None"] + list(saved_rubrics.keys()),
            help="Choose a rubric from the library to skip rubric upload/parsing.",
        )

    st.divider()

    # ── File uploads ─────────────────────────────────
    st.subheader("3 · Upload Files")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**Assignment Instructions**")
        instructions_file = st.file_uploader("PDF or DOCX",
                                             type=["pdf","docx"], key="instr")

    with c2:
        st.markdown("**Grading Rubric**")
        same_file = st.checkbox("Same as instructions")
        rubric_file = None
        if not same_file:
            rubric_file = st.file_uploader("PDF or DOCX",
                                           type=["pdf","docx"], key="rubric")

    with c3:
        st.markdown("**Student Submissions**")
        st.caption("Single file or ZIP with multiple submissions")
        submissions_uploads = st.file_uploader("PDF / DOCX / TWB / TWBX / ZIP",
                                               type=["pdf","docx","txt","zip","twb","twbx"],
                                               accept_multiple_files=True, key="subs")

    with st.expander("Optional: criteria and rubric library"):
        criteria_file = st.file_uploader("Criteria JSON", type=["json"], key="crit")
        save_to_library = st.checkbox("Save parsed criteria to Rubric Library after grading")
        rubric_library_name = st.text_input(
            "Library name",
            value=assignment_name if assignment_name else "",
            placeholder="e.g. Lab 01 Retail Analytics Rubric",
        )

    st.divider()

    # ── RAG + Validation + Run ───────────────────────
    c_rag, c_quality, c_run = st.columns([1.2, 1.4, 1.6])
    with c_rag:
        rag_mode = st.radio("RAG Mode", ["keyword", "semantic"], horizontal=True)
        evidence_label = st.selectbox(
            "Evidence Mode",
            ["Hybrid: RAG + full context", "RAG only", "Full context only"],
            help="Hybrid is recommended. It uses retrieved evidence but keeps full anonymized context as a safety net.",
        )
        evidence_mode = {
            "Hybrid: RAG + full context": "hybrid",
            "RAG only": "rag_only",
            "Full context only": "full_context",
        }[evidence_label]
        show_trace = st.checkbox("Show transparency preview", value=True)
        st.caption("Saves model inputs, anonymization log, RAG evidence, scores, and feedback.")

    with c_quality:
        scoring_preset = st.selectbox("Scoring Profile", list(SCORING_PRESETS), index=1)
        calibration_offset = st.number_input(
            "Calibration Offset",
            min_value=-10.0,
            max_value=10.0,
            value=0.0,
            step=0.5,
            help="Add points after grading to match a human-grader gold standard. Use 0 until calibrated.",
        )
        st.caption("Use Lenient TA when the model is under-scoring partial-credit work.")

    missing = []
    if not assignment_name.strip():                                           missing.append("assignment name")
    if not instructions_file:                                                 missing.append("instructions")
    if (saved_rubric_choice == "None" and not criteria_file
            and not same_file and not rubric_file):                           missing.append("rubric")
    if not submissions_uploads:                                               missing.append("submissions")
    if provider_key in ("openai","anthropic","huggingface") and not api_key: missing.append("API key")

    with c_run:
        if missing:
            st.warning(f"Missing: {' · '.join(missing)}")
        run_btn = st.button("▶  Run Grading", type="primary", disabled=bool(missing))

    # ── Pipeline ─────────────────────────────────────
    if run_btn:
        from document_reader import read_document, load_student_submissions
        from calibrated_grader import CalibratedGrader, OllamaClient, HuggingFaceClient, OpenAIClient
        from rubric_parser import parse_rubric_cached

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("ui_output") / safe_assignment_slug(assignment_name)
        run_dir = output_dir / "runs" / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as _tmp:
            tmp = Path(_tmp)
            instr_path  = save_upload(instructions_file, tmp)
            if saved_rubric_choice != "None" or criteria_file:
                rubric_path = instr_path
            else:
                rubric_path = instr_path if same_file else save_upload(rubric_file, tmp)
            sub_dir     = tmp / "submissions"; sub_dir.mkdir()
            for u in submissions_uploads:
                for p in extract_submissions(u, tmp):
                    shutil.copy(p, sub_dir / p.name)

            with st.status("Loading documents…") as s:
                instructions_text = read_document(str(instr_path))
                submissions       = load_student_submissions(str(sub_dir))
                s.update(label=f"✓ {len(submissions)} submission(s) loaded", state="complete")

            if not submissions:
                st.error("No valid submission files found."); st.stop()

            with st.status("Loading rubric criteria…") as s:
                criteria = None

                # 1 — saved rubric library (instant, no API call)
                if saved_rubric_choice != "None":
                    criteria = saved_rubrics[saved_rubric_choice]["criteria"]
                    s.update(label=f"✓ {len(criteria)} criteria from Rubric Library", state="complete")

                # 2 — uploaded JSON (instant, no API call)
                if criteria_file:
                    criteria = json.loads(criteria_file.getbuffer().decode())
                    s.update(label=f"✓ {len(criteria)} criteria from uploaded file", state="complete")

                # 3 — disk cache (instant if same rubric was parsed before)
                if criteria is None:
                    from memory_layer import file_hash, disk_get
                    criteria = disk_get(f"rubric_{file_hash(str(rubric_path))}")
                    if criteria:
                        s.update(label=f"✓ {len(criteria)} criteria from cache", state="complete")

                # 4 — parse via API (OpenAI preferred, fallback to Anthropic)
                if criteria is None and api_key:
                    parse_provider = provider_key if provider_key in ("openai","anthropic") else "openai"
                    s.update(label=f"Parsing rubric with {parse_provider} (one-time, ~10 sec)…",
                             state="running")
                    try:
                        criteria = parse_rubric_cached(
                            str(rubric_path),
                            provider=parse_provider,
                            api_key=api_key,
                        )
                        s.update(label=f"✓ {len(criteria)} criteria parsed and cached", state="complete")
                    except Exception as e:
                        st.error(f"Rubric parsing failed: {e}")
                        st.stop()

                if criteria is None:
                    st.error(
                        "Cannot grade without criteria.\n\n"
                        "**Quick fix:** expand **Advanced** above and upload "
                        "a saved criteria JSON from a previous run"
                    )
                    st.stop()

            if save_to_library and criteria:
                saved_path = save_rubric_to_library(
                    rubric_library_name or assignment_name,
                    criteria,
                    course=course_name,
                    outcomes=learning_outcomes,
                )
                st.info(f"Rubric criteria saved to {saved_path}")

            if show_trace:
                from privacy_processor import anonymize
                from rag_retriever import build_rag_evidence, build_rag_evidence_semantic
                from rubric_parser import build_rubric_prompt_section

                sample = submissions[0]
                sample_anon, sample_log = anonymize(sample["text"], known_name=sample["name"])
                if rag_mode == "semantic":
                    try:
                        sample_evidence = build_rag_evidence_semantic(sample_anon, criteria=criteria, top_n=2)
                    except Exception as e:
                        sample_evidence = f"Semantic preview unavailable: {e}"
                else:
                    sample_evidence = build_rag_evidence(sample_anon, criteria=criteria, top_n=2)
                sample_context = (
                    "(not supplied in RAG-only mode)"
                    if evidence_mode == "rag_only"
                    else sample_anon[:3500]
                )

                st.markdown("### Transparency Preview Before Grading")
                p1, p2, p3, p4, p5 = st.columns(5)
                p1.metric("Submissions", len(submissions))
                p2.metric("Criteria", len(criteria))
                p3.metric("Provider", provider_key)
                p4.metric("RAG", rag_mode)
                p5.metric("Mode", evidence_mode)

                with st.expander("Rubric criteria parsed for the model", expanded=False):
                    st.dataframe([
                        {
                            "Criterion": c.get("name", ""),
                            "Max points": c.get("max_points", ""),
                            "Description": c.get("description", ""),
                            "Keywords": ", ".join(c.get("keywords", [])[:12]) if isinstance(c.get("keywords"), list) else "",
                        }
                        for c in criteria
                    ], use_container_width=True, hide_index=True)

                with st.expander(f"Sample privacy + evidence preview: {sample['name']}", expanded=False):
                    st.markdown("**Anonymization actions**")
                    st.write(sample_log or ["No PII patterns detected in preview sample."])
                    st.markdown("**Anonymized text sample**")
                    st.code(sample_anon[:2500] or "(empty)", language="text")
                    st.markdown("**Evidence that will be supplied to the model**")
                    st.code(sample_evidence[:5000] or "(empty)", language="text")
                    st.markdown("**Submission context safety net**")
                    st.code(sample_context, language="text")

                with st.expander("Rubric section inserted into the system prompt", expanded=False):
                    st.code(build_rubric_prompt_section(criteria), language="text")

            if provider_key == "ollama" and not OllamaClient.check_connection():
                st.error("Ollama not running. Start with `ollama serve`."); st.stop()
            if provider_key == "huggingface" and not HuggingFaceClient.check_token(api_key):
                st.error("Invalid Hugging Face token."); st.stop()
            if provider_key == "openai" and not OpenAIClient.check_key(api_key):
                st.error("Invalid OpenAI API key."); st.stop()

            grader = CalibratedGrader(
                criteria=criteria, assignment_name=assignment_name,
                model=model_name, provider=provider_key,
                api_key=api_key, rag_mode=rag_mode,
                evidence_mode=evidence_mode,
                calibration_offset=calibration_offset,
                scoring_bands=SCORING_PRESETS[scoring_preset],
            )

            st.markdown(f"**Grading {len(submissions)} student(s) with `{model_name}`…**")
            progress = st.progress(0)
            live_tbl = st.empty()
            live_feedback = st.empty()
            live_rows, all_results = [], []

            for idx, sub in enumerate(submissions, 1):
                sid = f"Student_{idx:03d}"
                try:
                    result = grader.grade_submission(
                        instructions_text=instructions_text,
                        submission_text=sub["text"],
                        student_id=sid, student_name=sub["name"],
                    )
                    result["course_name"] = course_name
                    result["learning_outcomes"] = learning_outcomes
                except Exception as e:
                    st.warning(f"{sid}: {e}"); continue

                (run_dir / f"{sid}.json").write_text(json.dumps(result, indent=2))
                (output_dir / f"{sid}.json").write_text(json.dumps(result, indent=2))
                all_results.append(result)
                grade = result.get("letter_grade") or letter_grade(result.get("percentage",0))
                live_rows.append({
                    "Student": sid, "Name": sub["name"],
                    "Score": f"{result.get('total_score',0)}/{result.get('max_score','?')}",
                    "Grade": f"{GRADE_COLOR.get(grade,'')} {grade}",
                    "%": f"{result.get('percentage',0):.1f}%",
                    "Feedback": result.get("overall_feedback", "")[:180],
                })
                live_tbl.dataframe(live_rows, use_container_width=True, hide_index=True)
                live_feedback.info(f"{sid} feedback: {result.get('overall_feedback', '(no feedback returned)')}")
                progress.progress(idx / len(submissions))
                if idx < len(submissions): time.sleep(0.2)

            combined = output_dir / "all_results.json"
            run_combined = run_dir / "all_results.json"
            combined.write_text(json.dumps(all_results, indent=2))
            run_combined.write_text(json.dumps(all_results, indent=2))
            feedback_log, history_jsonl, history_csv, feedback_csv = write_feedback_artifacts(
                output_dir, all_results, run_id, provider_key, model_name, rag_mode
            )
            (run_dir / "feedback_log.csv").write_text(feedback_csv.read_text(encoding="utf-8"), encoding="utf-8")
            run_manifest = {
                "run_id": run_id,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "assignment_name": assignment_name,
                "course_name": course_name,
                "learning_outcomes": learning_outcomes,
                "provider": provider_key,
                "model": model_name,
                "rag_mode": rag_mode,
                "evidence_mode": evidence_mode,
                "scoring_preset": scoring_preset,
                "calibration_offset": calibration_offset,
                "submissions": len(all_results),
                "output_dir": str(output_dir),
                "run_dir": str(run_dir),
                "artifacts": {
                    "latest_results": str(combined),
                    "run_results": str(run_combined),
                    "feedback_history": str(history_jsonl),
                    "feedback_history_csv": str(history_csv),
                    "feedback_csv": str(feedback_csv),
                },
            }
            (run_dir / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
            st.session_state.update({
                "last_results":    all_results,
                "assignment_name": assignment_name,
                "output_dir":      str(output_dir),
                "run_dir":         str(run_dir),
                "feedback_log":    feedback_log,
                "run_manifest":    run_manifest,
            })
            st.success(f"✓ Done — {len(all_results)} students graded")

            dc1, dc2 = st.columns(2)
            with dc1:
                st.download_button("⬇ Download JSON", data=combined.read_bytes(),
                                   file_name="all_results.json", mime="application/json",
                                   key="grade_download_json")
            with dc2:
                buf = io.StringIO()
                csv.DictWriter(buf, fieldnames=list(live_rows[0])).writeheader()
                csv.DictWriter(buf, fieldnames=list(live_rows[0])).writerows(live_rows)
                st.download_button("⬇ Download CSV", data=buf.getvalue(),
                                   file_name="grading_summary.csv", mime="text/csv",
                                   key="grade_download_csv")
            st.caption(f"Saved run: {run_dir}")


# ═══════════════════════════════════════════════════
# TAB 2 — REVIEW QUEUE
# ═══════════════════════════════════════════════════
with tab2:
    results    = st.session_state.get("last_results")
    output_dir = st.session_state.get("output_dir")

    if not results:
        st.info("Run grading first, or load a previous results file.")
        loaded = st.file_uploader("Load all_results.json", type=["json"], key="load_res")
        if loaded:
            results = json.loads(loaded.getbuffer())
            st.session_state["last_results"] = results

    if results:
        st.subheader("Review Queue")
        output_dir = st.session_state.get("output_dir") or output_dir
        if "review_status" not in st.session_state:
            st.session_state["review_status"] = load_review_status(output_dir)
        review_status = st.session_state["review_status"]

        max_score = results[0].get("max_score", 20)
        scores = [r.get("total_score", 0) for r in results]
        pcts   = [r.get("percentage",  0) for r in results]
        grades = [r.get("letter_grade") or letter_grade(p) for r, p in zip(results, pcts)]
        queue_rows = review_rows(results, review_status)
        approved_count = sum(1 for row in queue_rows if row["Status"] == "Approved")
        needs_review_count = sum(1 for row in queue_rows if row["Status"] == "Needs Review")

        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Reviewed", f"{approved_count}/{len(results)}")
        q2.metric("Needs Review", needs_review_count)
        q3.metric("Ready", sum(1 for row in queue_rows if row["Status"] == "Ready"))
        q4.metric("Avg Score", f"{sum(scores)/len(scores):.1f}/{max_score}")

        status_filter = st.segmented_control(
            "Queue filter",
            ["All", "Needs Review", "Ready", "Approved"],
            default="All",
            key="review_queue_filter",
        )
        filtered_rows = [
            row for row in queue_rows
            if status_filter == "All" or row["Status"] == status_filter
        ]
        st.dataframe(filtered_rows, use_container_width=True, hide_index=True)

        selectable_ids = [row["Student"] for row in filtered_rows] or [r.get("student_id", "") for r in results]
        selected_review_sid = st.selectbox("Review student", selectable_ids, key="review_student")
        selected_idx = next(
            (idx for idx, r in enumerate(results) if r.get("student_id") == selected_review_sid),
            0,
        )
        selected = results[selected_idx]
        selected_criteria = selected.get("criteria", [])

        st.markdown("### Fast Review")
        rq1, rq2 = st.columns([1, 1])
        with rq1:
            st.metric("AI Score", f"{selected.get('total_score', 0)}/{selected.get('max_score', max_score)}")
            st.metric("Confidence", f"{selected.get('confidence_score', 100)}%")
            st.caption(f"Status: {result_status(selected, review_status)}")
            flags = selected.get("review_flags", [])
            if flags:
                st.warning("Review flags: " + " · ".join(flags))
            reviewed_feedback = st.text_area(
                "Overall feedback",
                value=selected.get("overall_feedback", ""),
                height=150,
                key=f"rq_feedback_{selected_review_sid}",
            )
        with rq2:
            st.markdown("**Criterion scores**")
            reviewed_criteria = []
            reviewed_scores = []
            for j, c in enumerate(selected_criteria):
                cmax = float(c.get("max_points", 1))
                pts = st.number_input(
                    f"{c.get('name', f'Criterion {j+1}')} /{cmax:g}",
                    min_value=0.0,
                    max_value=cmax,
                    value=float(c.get("awarded_points", 0)),
                    step=0.5,
                    key=f"rq_pts_{selected_review_sid}_{j}",
                )
                reviewed_scores.append(pts)
                reviewed_criteria.append({**c, "awarded_points": pts})

        rqa, rqb, rqc = st.columns(3)
        if rqa.button("Save Review Edits", key=f"rq_save_{selected_review_sid}", type="primary"):
            new_total = round(sum(reviewed_scores), 1)
            new_pct = round(new_total / max_score * 100, 1) if max_score else 0
            updated = {
                **selected,
                "criteria": reviewed_criteria,
                "overall_feedback": reviewed_feedback,
                "total_score": new_total,
                "percentage": new_pct,
                "letter_grade": letter_grade(new_pct),
            }
            results[selected_idx] = updated
            st.session_state["last_results"] = results
            if output_dir:
                Path(output_dir, f"{selected_review_sid}.json").write_text(json.dumps(updated, indent=2))
                Path(output_dir, "all_results.json").write_text(json.dumps(results, indent=2))
                write_feedback_artifacts(
                    Path(output_dir), results,
                    f"review_edit_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    updated.get("model_trace", {}).get("provider", ""),
                    updated.get("model_trace", {}).get("model", ""),
                    updated.get("model_trace", {}).get("rag_mode", ""),
                )
            st.success(f"Saved edits for {selected_review_sid}")
            st.rerun()

        if rqb.button("Approve Student", key=f"rq_approve_{selected_review_sid}"):
            review_status[selected_review_sid] = "approved"
            st.session_state["review_status"] = review_status
            save_review_status(output_dir, review_status)
            st.success(f"{selected_review_sid} approved")
            st.rerun()

        if rqc.button("Send Back To Review", key=f"rq_unapprove_{selected_review_sid}"):
            review_status.pop(selected_review_sid, None)
            st.session_state["review_status"] = review_status
            save_review_status(output_dir, review_status)
            st.info(f"{selected_review_sid} returned to review queue")
            st.rerun()

        approved_rows = [
            r for r in results
            if review_status.get(r.get("student_id", "")) == "approved"
        ]
        if approved_rows:
            approved_buf = io.StringIO()
            writer = csv.writer(approved_buf)
            writer.writerow(["student_id", "score", "max_score", "percentage", "letter_grade", "overall_feedback"])
            for r in approved_rows:
                pct = r.get("percentage", 0)
                writer.writerow([
                    r.get("student_id", ""),
                    r.get("total_score", 0),
                    r.get("max_score", max_score),
                    pct,
                    r.get("letter_grade") or letter_grade(pct),
                    r.get("overall_feedback", ""),
                ])
            st.download_button(
                "⬇ Download Approved Grades CSV",
                data=approved_buf.getvalue(),
                file_name="approved_grades.csv",
                mime="text/csv",
                key="review_download_approved_grades",
            )

        st.divider()
        st.subheader("Results Archive")

        # ── Summary metrics ───────────────────────────
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Students",   len(results))
        m2.metric("Avg Score",  f"{sum(scores)/len(scores):.1f}/{max_score}")
        m3.metric("Avg %",      f"{sum(pcts)/len(pcts):.1f}%")
        m4.metric("Top Grade",  max(set(grades), key=grades.count))

        st.divider()

        dist = Counter(grades)
        grade_order = [g for g in ["A","A-","B+","B","B-","C+","C","C-","D","F"] if g in dist]
        if grade_order:
            st.subheader("Grade Distribution")
            st.bar_chart({g: dist[g] for g in grade_order}, height=200, color="#006747")

        st.divider()

        # ── Download buttons ──────────────────────────
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button("⬇ Download JSON", data=json.dumps(results, indent=2),
                               file_name="all_results.json", mime="application/json",
                               key="review_download_json")
        with dl2:
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["Student", "Score", "Max", "%", "Grade"])
            for r in results:
                g = r.get("letter_grade") or letter_grade(r.get("percentage", 0))
                w.writerow([r["student_id"], r.get("total_score",0),
                            r.get("max_score", max_score),
                            f"{r.get('percentage',0):.1f}", g])
            st.download_button("⬇ Download CSV", data=buf.getvalue(),
                               file_name="grading_summary.csv", mime="text/csv",
                               key="review_download_summary_csv")

        st.divider()
        st.subheader("All Feedback")
        st.caption("Every overall and criterion-level feedback item in one table for review and model comparison.")
        feedback_rows = feedback_records(results)
        if feedback_rows:
            st.dataframe(feedback_rows, use_container_width=True, hide_index=True)
            fb_buf = io.StringIO()
            fb_fields = [
                "run_id", "timestamp", "assignment", "student_id", "provider", "model", "rag_mode", "evidence_mode",
                "total_score", "max_score", "percentage", "letter_grade", "confidence_score", "review_flags", "overall_feedback",
                "criterion", "criterion_score", "criterion_max", "completed", "missing_or_weak", "suggestion",
            ]
            fb_writer = csv.DictWriter(fb_buf, fieldnames=fb_fields)
            fb_writer.writeheader()
            fb_writer.writerows(feedback_rows)
            st.download_button("⬇ Download Feedback Log CSV",
                               data=fb_buf.getvalue(),
                               file_name="feedback_log.csv",
                               mime="text/csv",
                               key="review_download_feedback_log")

        with st.expander("Model input transparency for this result set", expanded=False):
            trace_options = {
                r.get("student_id", f"Student_{i+1:03d}"): r
                for i, r in enumerate(results)
                if r.get("model_trace")
            }
            if not trace_options:
                st.info("No model trace found. New grading runs will save provider, prompt, RAG evidence, and message payloads.")
            else:
                selected_sid = st.selectbox("Student trace", list(trace_options), key="trace_student_select")
                trace = trace_options[selected_sid].get("model_trace", {})
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("Provider", trace.get("provider", ""))
                t2.metric("Model", trace.get("model", ""))
                t3.metric("RAG", trace.get("rag_mode", ""))
                t4.metric("Evidence chars", trace.get("rag_evidence_chars_sent", 0))
                st.markdown("**Anonymization log**")
                st.write(trace.get("anonymization_log", []))
                st.markdown("**System prompt sent to model**")
                st.code(trace.get("system_prompt", ""), language="text")
                st.markdown("**Student prompt sent to model**")
                st.code(trace.get("student_prompt", ""), language="text")

        st.divider()
        st.subheader("Student Results  —  click to review & edit")

        # ── Per-student editable cards ────────────────
        for i, r in enumerate(results):
            pct   = r.get("percentage", 0)
            grade = r.get("letter_grade") or letter_grade(pct)
            icon  = GRADE_COLOR.get(grade, "")

            with st.expander(
                f"{icon}  {r['student_id']}  ·  "
                f"{r.get('total_score',0)}/{max_score} pts  ·  "
                f"{pct:.1f}%  ·  Grade: {grade}",
                expanded=False,
            ):
                crit_list = [c for c in r.get("criteria", []) if "awarded_points" in c]

                # ── Overall feedback (editable) ───────
                new_feedback = st.text_area(
                    "Overall Feedback",
                    value=r.get("overall_feedback", ""),
                    key=f"fb_{i}",
                    height=90,
                    help="Edit the overall feedback that will be shown to the student",
                )

                st.markdown("---")
                st.markdown("**Criterion Scores & Feedback**")

                new_scores   = []
                new_criteria = []

                for j, c in enumerate(crit_list):
                    cmax    = c.get("max_points", 1)
                    awarded = float(c.get("awarded_points", 0))

                    # Score row
                    sc1, sc2, sc3 = st.columns([3, 1, 1])
                    with sc1:
                        st.markdown(f"**{c['name']}**")
                    with sc2:
                        new_pts = st.number_input(
                            "pts", min_value=0.0, max_value=float(cmax),
                            value=awarded, step=0.5,
                            key=f"pts_{i}_{j}", label_visibility="collapsed",
                        )
                    with sc3:
                        st.markdown(f"<span style='color:#6b8c7a;font-size:0.85rem'>/ {cmax}</span>",
                                    unsafe_allow_html=True)

                    st.progress(new_pts / cmax if cmax else 0)

                    # Feedback fields
                    f1, f2 = st.columns(2)
                    with f1:
                        new_completed = st.text_area(
                            "✔ What was done", value=c.get("completed", ""),
                            key=f"done_{i}_{j}", height=70,
                        )
                        new_missing = st.text_area(
                            "⚠ Missing / weak", value=c.get("missing_or_weak", ""),
                            key=f"miss_{i}_{j}", height=70,
                        )
                    with f2:
                        new_suggestion = st.text_area(
                            "💡 Suggestion", value=c.get("suggestion", ""),
                            key=f"sug_{i}_{j}", height=70,
                        )

                    new_scores.append(new_pts)
                    new_criteria.append({**c,
                        "awarded_points":  new_pts,
                        "completed":       new_completed,
                        "missing_or_weak": new_missing,
                        "suggestion":      new_suggestion,
                    })
                    st.markdown("---")

                # ── Save button ───────────────────────
                if st.button("💾  Save Changes", key=f"save_{i}", type="primary"):
                    new_total = round(sum(new_scores), 1)
                    new_pct   = round(new_total / max_score * 100, 1) if max_score else 0.0
                    new_grade = letter_grade(new_pct)

                    updated = {**r,
                        "criteria":         new_criteria,
                        "overall_feedback": new_feedback,
                        "total_score":      new_total,
                        "percentage":       new_pct,
                        "letter_grade":     new_grade,
                    }
                    results[i] = updated
                    st.session_state["last_results"] = results

                    # Persist to disk
                    if output_dir:
                        Path(output_dir, f"{r['student_id']}.json").write_text(
                            json.dumps(updated, indent=2))
                        Path(output_dir, "all_results.json").write_text(
                            json.dumps(results, indent=2))
                        edit_run_id = f"manual_edit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        write_feedback_artifacts(
                            Path(output_dir), results, edit_run_id,
                            updated.get("model_trace", {}).get("provider", ""),
                            updated.get("model_trace", {}).get("model", ""),
                            updated.get("model_trace", {}).get("rag_mode", ""),
                        )

                    st.success(f"✓ {r['student_id']} updated — {new_total}/{max_score} ({new_grade})")
                    st.rerun()


# ═══════════════════════════════════════════════════
# TAB 3 — CLASS ANALYTICS
# ═══════════════════════════════════════════════════
with tab3:
    st.subheader("Class Analytics")
    st.caption("CoGrader-style class view: grade distribution, weakest criteria, and review priorities.")

    analytics_results = st.session_state.get("last_results")
    analytics_load = st.file_uploader("Load all_results.json for analytics", type=["json"], key="analytics_load")
    if analytics_load:
        analytics_results = json.loads(analytics_load.getbuffer())
        st.session_state["last_results"] = analytics_results

    if not analytics_results:
        st.info("Run grading or load an `all_results.json` file to see class analytics.")
    else:
        max_score = analytics_results[0].get("max_score", 20)
        scores = [float(r.get("total_score", 0)) for r in analytics_results]
        pcts = [float(r.get("percentage", 0)) for r in analytics_results]
        grades = [r.get("letter_grade") or letter_grade(r.get("percentage", 0)) for r in analytics_results]
        review_status = st.session_state.get("review_status", {})

        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Students", len(analytics_results))
        a2.metric("Average", f"{sum(scores)/len(scores):.1f}/{max_score}")
        a3.metric("Lowest", f"{min(scores):.1f}/{max_score}")
        a4.metric("Approved", sum(1 for r in analytics_results if review_status.get(r.get("student_id")) == "approved"))

        st.divider()
        ga, gb = st.columns([1, 1])
        with ga:
            st.markdown("### Grade Distribution")
            dist = Counter(grades)
            grade_order = [g for g in ["A","A-","B+","B","B-","C+","C","C-","D","F"] if g in dist]
            st.bar_chart({g: dist[g] for g in grade_order}, height=260, color="#006747")
        with gb:
            st.markdown("### Review Priority")
            priority_rows = review_rows(analytics_results, review_status)
            priority_rows = sorted(
                priority_rows,
                key=lambda row: (row["Status"] != "Needs Review", row["%"]),
            )
            st.dataframe(priority_rows[:10], use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("### Criterion-Level Gaps")
        criterion_stats = {}
        gap_notes = []
        for r in analytics_results:
            for c in r.get("criteria", []):
                name = c.get("name", "")
                cmax = float(c.get("max_points", 0) or 0)
                pts = float(c.get("awarded_points", 0) or 0)
                if not name or cmax <= 0:
                    continue
                item = criterion_stats.setdefault(name, {"scores": [], "max": cmax, "weak": 0})
                item["scores"].append(pts)
                if pts < cmax * 0.75:
                    item["weak"] += 1
                note = c.get("missing_or_weak", "")
                if note:
                    gap_notes.append({
                        "Student": r.get("student_id", ""),
                        "Criterion": name,
                        "Missing / weak": note,
                        "Suggestion": c.get("suggestion", ""),
                    })

        criterion_rows = []
        for name, item in criterion_stats.items():
            avg = sum(item["scores"]) / len(item["scores"])
            cmax = item["max"]
            criterion_rows.append({
                "Criterion": name,
                "Avg score": round(avg, 2),
                "Max": cmax,
                "Avg %": f"{avg / cmax * 100:.1f}%",
                "Students below 75%": item["weak"],
            })
        criterion_rows = sorted(criterion_rows, key=lambda row: float(row["Avg %"].rstrip("%")))
        st.dataframe(criterion_rows, use_container_width=True, hide_index=True)

        if gap_notes:
            st.markdown("### Common Feedback Themes")
            st.dataframe(gap_notes[:50], use_container_width=True, hide_index=True)

        analytics_buf = io.StringIO()
        fields = ["Criterion", "Avg score", "Max", "Avg %", "Students below 75%"]
        writer = csv.DictWriter(analytics_buf, fieldnames=fields)
        writer.writeheader()
        writer.writerows(criterion_rows)
        st.download_button(
            "⬇ Download Analytics CSV",
            data=analytics_buf.getvalue(),
            file_name="class_analytics.csv",
            mime="text/csv",
            key="analytics_download_csv",
        )


# ═══════════════════════════════════════════════════
# TAB 4 — RUBRIC LIBRARY
# ═══════════════════════════════════════════════════
with tab4:
    st.subheader("Rubric Library")
    st.caption("Save reusable rubric criteria so future assignments can skip rubric parsing and grade faster.")

    library = load_rubric_library()
    lib1, lib2 = st.columns([1, 1])

    with lib1:
        st.markdown("### Saved Rubrics")
        if not library:
            st.info("No saved rubrics yet. Save one from the Grade tab or upload criteria below.")
        else:
            selected_rubric = st.selectbox("Rubric", list(library.keys()), key="library_select")
            item = library[selected_rubric]
            st.metric("Criteria", len(item.get("criteria", [])))
            st.caption(f"Course: {item.get('course', '') or 'Not set'}")
            st.caption(f"Saved: {item.get('saved_at', '') or 'Unknown'}")
            st.dataframe([
                {
                    "Criterion": c.get("name", ""),
                    "Max": c.get("max_points", ""),
                    "Description": c.get("description", ""),
                    "Keywords": ", ".join(c.get("keywords", [])[:10]) if isinstance(c.get("keywords"), list) else "",
                }
                for c in item.get("criteria", [])
            ], use_container_width=True, hide_index=True)
            st.download_button(
                "⬇ Download Rubric JSON",
                data=json.dumps(item, indent=2),
                file_name=f"{safe_assignment_slug(selected_rubric)}.json",
                mime="application/json",
                key=f"library_download_rubric_{safe_assignment_slug(selected_rubric)}",
            )

    with lib2:
        st.markdown("### Add To Library")
        current_results = st.session_state.get("last_results")
        source = st.radio("Source", ["Current result set", "Upload criteria JSON"], horizontal=True)
        lib_name = st.text_input("Rubric name", placeholder="e.g. Lab 01 Business Analytics Rubric")
        lib_course = st.text_input("Course", placeholder="e.g. CAI 3801")
        lib_outcomes = st.text_input("Learning outcomes", placeholder="e.g. LO1, LO2")

        criteria_to_save = None
        if source == "Current result set":
            if current_results:
                criteria_to_save = criteria_from_result(current_results[0])
                st.success(f"{len(criteria_to_save)} criteria available from current results.")
            else:
                st.info("Run grading or load results first.")
        else:
            uploaded_criteria = st.file_uploader("Criteria JSON", type=["json"], key="library_upload")
            if uploaded_criteria:
                payload = json.loads(uploaded_criteria.getbuffer())
                criteria_to_save = payload.get("criteria", payload) if isinstance(payload, dict) else payload
                st.success(f"{len(criteria_to_save)} criteria loaded from upload.")

        if st.button("Save Rubric", type="primary", disabled=not (lib_name and criteria_to_save)):
            path = save_rubric_to_library(lib_name, criteria_to_save, lib_course, lib_outcomes)
            st.success(f"Saved rubric to {path}")
            st.rerun()


# ═══════════════════════════════════════════════════
# TAB 5 — COMPARISON
# ═══════════════════════════════════════════════════
with tab5:
    st.subheader("Compare Two Models")
    st.caption("Upload result files from two different providers to compare accuracy and cost.")

    cc1, cc2 = st.columns(2)
    with cc1:
        fl_label = st.text_input("Model A label", value="GPT-4o-mini")
        f_file   = st.file_uploader("Model A — all_results.json", type=["json"], key="cf")
    with cc2:
        ll_label = st.text_input("Model B label", value="Qwen2.5-7B (HF)")
        l_file   = st.file_uploader("Model B — all_results.json", type=["json"], key="cl")

    if f_file and l_file:
        frontier = {r["student_id"]:r for r in json.loads(f_file.getbuffer())}
        local    = {r["student_id"]:r for r in json.loads(l_file.getbuffer())}
        common   = sorted(s for s in frontier if s in local)

        if not common:
            st.error("No matching student IDs found.")
        else:
            rows = []
            for sid in common:
                fs = frontier[sid].get("total_score",0)
                ls = local[sid].get("total_score",0)
                d  = round(ls - fs, 1)
                rows.append({
                    "Student":    sid,
                    fl_label:     fs,
                    ll_label:     ls,
                    "Diff":       d,
                    "_agree":     abs(d) <= 2,
                    "_gm":        frontier[sid].get("letter_grade") == local[sid].get("letter_grade"),
                })

            n = len(rows)
            fa = sum(r[fl_label] for r in rows)/n
            la = sum(r[ll_label] for r in rows)/n
            ag = sum(r["Diff"] for r in rows)/n
            ap = sum(1 for r in rows if r["_agree"])/n*100
            ms = next(iter(frontier.values())).get("max_score",20)

            m1,m2,m3,m4 = st.columns(4)
            m1.metric(f"{fl_label} avg", f"{fa:.1f}/{ms}")
            m2.metric(f"{ll_label} avg", f"{la:.1f}/{ms}")
            m3.metric("Avg gap", f"{ag:+.2f} pts")
            m4.metric("Within ±2 pts", f"{ap:.0f}%")

            st.divider()
            st.dataframe([{
                "Student":    r["Student"],
                fl_label:     r[fl_label],
                ll_label:     r[ll_label],
                "Diff":       f"{r['Diff']:+.1f}",
                "Score ±2":   "✅" if r["_agree"] else "❌",
                "Same grade": "✅" if r["_gm"]    else "❌",
            } for r in rows], use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Feedback Comparison")
            compare_sid = st.selectbox("Student", common, key="feedback_compare_sid")
            left_result = frontier[compare_sid]
            right_result = local[compare_sid]

            fc1, fc2 = st.columns(2)
            with fc1:
                st.markdown(f"**{fl_label}**")
                st.metric("Score", f"{left_result.get('total_score', 0)}/{ms}")
                st.text_area("Overall feedback", value=left_result.get("overall_feedback", ""),
                             height=120, key=f"fb_left_{compare_sid}")
            with fc2:
                st.markdown(f"**{ll_label}**")
                st.metric("Score", f"{right_result.get('total_score', 0)}/{ms}")
                st.text_area("Overall feedback", value=right_result.get("overall_feedback", ""),
                             height=120, key=f"fb_right_{compare_sid}")

            left_criteria = {c.get("name", ""): c for c in left_result.get("criteria", [])}
            right_criteria = {c.get("name", ""): c for c in right_result.get("criteria", [])}
            crit_names = sorted(set(left_criteria) | set(right_criteria))
            feedback_compare_rows = []
            for cname in crit_names:
                lc = left_criteria.get(cname, {})
                rc = right_criteria.get(cname, {})
                feedback_compare_rows.append({
                    "Criterion": cname,
                    f"{fl_label} score": lc.get("awarded_points", ""),
                    f"{ll_label} score": rc.get("awarded_points", ""),
                    "Score diff": (
                        round(float(rc.get("awarded_points", 0)) - float(lc.get("awarded_points", 0)), 1)
                        if lc or rc else ""
                    ),
                    f"{fl_label} feedback": " ".join([
                        str(lc.get("completed", "")),
                        str(lc.get("missing_or_weak", "")),
                        str(lc.get("suggestion", "")),
                    ]).strip(),
                    f"{ll_label} feedback": " ".join([
                        str(rc.get("completed", "")),
                        str(rc.get("missing_or_weak", "")),
                        str(rc.get("suggestion", "")),
                    ]).strip(),
                })
            st.dataframe(feedback_compare_rows, use_container_width=True, hide_index=True)

            with st.expander("Compare saved model inputs for this student", expanded=False):
                tc1, tc2 = st.columns(2)
                with tc1:
                    st.markdown(f"**{fl_label} model input**")
                    st.code(left_result.get("model_trace", {}).get("student_prompt", "No trace saved."), language="text")
                with tc2:
                    st.markdown(f"**{ll_label} model input**")
                    st.code(right_result.get("model_trace", {}).get("student_prompt", "No trace saved."), language="text")

            st.divider()
            st.subheader("Cost Comparison")
            co1, co2 = st.columns(2)
            co1.metric(fl_label, f"~${n*0.01:.2f}", "~$0.01 per student")
            co2.metric(ll_label, "$0.00", "Free — HF serverless")


# ═══════════════════════════════════════════════════
# TAB 6 — EVALUATE & PUBLISH
# ═══════════════════════════════════════════════════
with tab6:
    st.subheader("Evaluate & Publish")
    st.caption("Fill in human gold standard scores, run statistical evaluation, and track publication gaps.")

    st.divider()

    # ── Section A: Gold Standard Entry ───────────────
    st.markdown("### Step 1 — Enter Human Gold Standard Scores")
    st.caption("Fill in your scores for each student. These are compared against AI scores to compute QWK, MAE, and p-values.")

    ai_results = st.session_state.get("last_results")
    gs_load = st.file_uploader("Load existing all_results.json (if not graded this session)",
                                type=["json"], key="gs_ai")
    if gs_load and not ai_results:
        ai_results = json.loads(gs_load.getbuffer())
        st.session_state["last_results"] = ai_results

    if ai_results:
        max_score  = ai_results[0].get("max_score", 20)
        crit_names = [c["name"] for c in ai_results[0].get("rubric_criteria",
                      ai_results[0].get("criteria", []))
                      if "max_points" in c]
        crit_max   = {c["name"]: c["max_points"]
                      for c in ai_results[0].get("rubric_criteria",
                      ai_results[0].get("criteria", []))
                      if "max_points" in c}

        if "gold_standard" not in st.session_state:
            st.session_state["gold_standard"] = {}

        gs = st.session_state["gold_standard"]

        with st.form("gold_standard_form"):
            for r in ai_results:
                sid    = r["student_id"]
                ai_tot = r.get("total_score", 0)
                existing = gs.get(sid, {})

                with st.expander(f"{sid}  —  AI scored {ai_tot}/{max_score}  "
                                 f"{'✅ scored' if sid in gs else '⬜ not yet scored'}"):
                    cols = st.columns(len(crit_names))
                    scores = {}
                    for col, cname in zip(cols, crit_names):
                        cmax = crit_max.get(cname, 0)
                        scores[cname] = col.number_input(
                            f"{cname} /{cmax}",
                            min_value=0.0, max_value=float(cmax),
                            value=float(existing.get(cname, 0)),
                            step=0.5, key=f"gs_{sid}_{cname}",
                        )
                    gs[sid] = scores

            submitted = st.form_submit_button("Save All Scores", type="primary")
            if submitted:
                st.session_state["gold_standard"] = gs
                filled = sum(1 for s in gs.values() if any(v > 0 for v in s.values()))
                st.success(f"Saved — {filled}/{len(ai_results)} students scored")

        # Download gold standard CSV
        if gs:
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["student_id"] + crit_names + ["notes"])
            for r in ai_results:
                sid = r["student_id"]
                row_scores = gs.get(sid, {})
                w.writerow([sid] + [row_scores.get(c, "") for c in crit_names] + [""])
            st.download_button("⬇ Download Gold Standard CSV",
                               data=buf.getvalue(),
                               file_name="gold_standard.csv",
                               mime="text/csv",
                               key="evaluate_download_gold_standard")

    st.divider()

    # ── Section B: Run Evaluation ─────────────────────
    st.markdown("### Step 2 — Run Statistical Evaluation")

    gs_csv  = st.file_uploader("Upload Gold Standard CSV", type=["csv"], key="gs_csv")
    ai_json = st.file_uploader("Upload AI Results JSON",   type=["json"], key="eval_ai")

    if gs_csv and ai_json:
        if st.button("Run Evaluation", type="primary"):
            import tempfile as _tmp
            from evaluator import load_human_grades, load_ai_grades, compute_metrics, generate_report

            with _tmp.TemporaryDirectory() as td:
                csv_path  = Path(td) / "gold.csv"
                json_path = Path(td) / "ai.json"
                report_path = Path(td) / "report.txt"
                csv_path.write_bytes(gs_csv.getbuffer())
                json_path.write_bytes(ai_json.getbuffer())

                try:
                    human   = load_human_grades(str(csv_path))
                    ai      = load_ai_grades(str(json_path))
                    metrics = compute_metrics(human, ai)
                    generate_report(metrics, str(report_path))
                    ov = metrics["overall"]

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("QWK", ov["qwk"], f"Benchmark ≥0.68")
                    m2.metric("MAE", f"{ov['mae']} pts",
                              f"95% CI [{ov['mae_ci_95'][0]}, {ov['mae_ci_95'][1]}]")
                    m3.metric("Pearson r", ov["correlation"],
                              f"p={ov['correlation_pvalue']}")
                    m4.metric("AI Bias", f"{ov['bias']:+.2f} pts",
                              f"p={ov['bias_pvalue']} {'sig.' if ov['bias_pvalue']<0.05 else 'n.s.'}")

                    st.divider()
                    st.markdown("**Per-criterion breakdown**")
                    st.dataframe([
                        {"Criterion": c,
                         "MAE": m["mae"],
                         "Bias": m["bias"],
                         "Pearson r": m["correlation"],
                         "QWK": m["qwk"],
                         "Within ±1pt": f"{m['within_1pt_pct']}%"}
                        for c, m in metrics["per_criterion"].items()
                    ], use_container_width=True, hide_index=True)

                    st.download_button("⬇ Download Full Report",
                                       data=report_path.read_text(),
                                       file_name="evaluation_report.txt",
                                       key="evaluate_download_report")
                except Exception as e:
                    st.error(f"Evaluation failed: {e}")

    st.divider()

    # ── Section C: Publication Checklist ──────────────
    st.markdown("### Publication Readiness Checklist")

    n_gold = len(st.session_state.get("gold_standard", {}))
    n_ai   = len(ai_results) if ai_results else 0

    checks = [
        (n_gold >= 15,      f"Gold standard: {n_gold}/15 students scored  (need all 15 for publication)"),
        (n_gold >= 50,      f"Sample size: {n_gold} students  (published papers use 110–701)"),
        (False,             "QWK ≥ 0.68  (run evaluation above after filling all scores)"),
        (False,             "Semantic RAG evaluated  (run: python run_experiments.py --run set5)"),
        (False,             "HF model comparison (15 students)  (run: python run_experiments.py --run hf)"),
        (False,             "Few-shot examples rebuilt  (run: python run_experiments.py --run shots)"),
        (True,              "FERPA-compliant privacy layer  ✓ done"),
        (True,              "Multi-model support  ✓ done"),
        (True,              "Statistical tests (p-values, CI)  ✓ done"),
        (True,              "Live deployed UI  ✓ done"),
    ]

    done = sum(1 for ok, _ in checks if ok)
    st.progress(done / len(checks))
    st.caption(f"{done}/{len(checks)} items complete")
    st.markdown("")

    for ok, label in checks:
        icon = "✅" if ok else "⬜"
        st.markdown(f"{icon}  {label}")
