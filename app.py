"""
app.py — BullsEye  (Streamlit UI — USF Theme)
Run:  streamlit run app.py
"""

import json, os, shutil, tempfile, time, zipfile, csv, io
from pathlib import Path
from collections import Counter
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
    nav = st.radio("", ["Grade Submissions", "View Results", "Model Comparison"],
                   label_visibility="collapsed")

    st.divider()
    st.markdown("**Quick Tips**")
    st.caption("• Upload a criteria JSON to skip rubric parsing")
    st.caption("• ZIP multiple submissions into one file")
    st.caption("• Edit any grade in View Results tab")
    st.caption("• Save changes to update the output files")

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
                      if p.is_file() and p.suffix.lower() in {".pdf",".docx",".doc",".txt"}
                      and not p.name.startswith((".", "__")))
    return [saved]

def letter_grade(pct):
    for t, g in [(93,"A"),(90,"A-"),(87,"B+"),(83,"B"),(80,"B-"),
                 (77,"C+"),(73,"C"),(70,"C-"),(60,"D")]:
        if pct >= t: return g
    return "F"

GRADE_COLOR = {"A":"🟢","A-":"🟢","B+":"🔵","B":"🔵","B-":"🔵",
               "C+":"🟡","C":"🟡","C-":"🟡","D":"🟠","F":"🔴"}

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
tab1, tab2, tab3 = st.tabs(["Grade Submissions", "View Results", "Model Comparison"])


# ═══════════════════════════════════════════════════
# TAB 1 — GRADE
# ═══════════════════════════════════════════════════
with tab1:

    # ── Provider ────────────────────────────────────
    st.subheader("1 · Choose AI Provider")
    provider_choice = st.radio(
        "", ["GPT (OpenAI)", "Claude (Anthropic)", "Hugging Face · Free", "Ollama · Local"],
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

    st.divider()

    # ── File uploads ─────────────────────────────────
    st.subheader("3 · Upload Files")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**Assignment Instructions**")
        instructions_file = st.file_uploader("PDF or DOCX",
                                             type=["pdf","docx","doc"], key="instr")

    with c2:
        st.markdown("**Grading Rubric**")
        same_file = st.checkbox("Same as instructions")
        rubric_file = None
        if not same_file:
            rubric_file = st.file_uploader("PDF or DOCX",
                                           type=["pdf","docx","doc"], key="rubric")

    with c3:
        st.markdown("**Student Submissions**")
        st.caption("Single file or ZIP with multiple submissions")
        submissions_uploads = st.file_uploader("PDF / DOCX / ZIP",
                                               type=["pdf","docx","doc","txt","zip"],
                                               accept_multiple_files=True, key="subs")

    with st.expander("Optional: upload pre-parsed criteria JSON (skips rubric API call)"):
        criteria_file = st.file_uploader("Criteria JSON", type=["json"], key="crit")

    st.divider()

    # ── RAG + Validation + Run ───────────────────────
    c_rag, c_run = st.columns([1, 2])
    with c_rag:
        rag_mode = st.radio("RAG Mode", ["keyword", "semantic"], horizontal=True)

    missing = []
    if not assignment_name.strip():                                           missing.append("assignment name")
    if not instructions_file:                                                 missing.append("instructions")
    if not same_file and not rubric_file:                                     missing.append("rubric")
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

        output_dir = Path("ui_output") / assignment_name.strip().replace(" ","_").replace("/","-")
        output_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as _tmp:
            tmp = Path(_tmp)
            instr_path  = save_upload(instructions_file, tmp)
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

                # 1 — uploaded JSON (instant, no API call)
                if criteria_file:
                    criteria = json.loads(criteria_file.getbuffer().decode())
                    s.update(label=f"✓ {len(criteria)} criteria from uploaded file", state="complete")

                # 2 — disk cache (instant if same rubric was parsed before)
                if criteria is None:
                    from memory_layer import file_hash, disk_get
                    criteria = disk_get(f"rubric_{file_hash(str(rubric_path))}")
                    if criteria:
                        s.update(label=f"✓ {len(criteria)} criteria from cache", state="complete")

                # 3 — parse via API (OpenAI preferred, fallback to Anthropic)
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
            )

            st.markdown(f"**Grading {len(submissions)} student(s) with `{model_name}`…**")
            progress = st.progress(0)
            live_tbl = st.empty()
            live_rows, all_results = [], []

            for idx, sub in enumerate(submissions, 1):
                sid = f"Student_{idx:03d}"
                try:
                    result = grader.grade_submission(
                        instructions_text=instructions_text,
                        submission_text=sub["text"],
                        student_id=sid, student_name=sub["name"],
                    )
                except Exception as e:
                    st.warning(f"{sid}: {e}"); continue

                (output_dir / f"{sid}.json").write_text(json.dumps(result, indent=2))
                all_results.append(result)
                grade = result.get("letter_grade") or letter_grade(result.get("percentage",0))
                live_rows.append({
                    "Student": sid, "Name": sub["name"],
                    "Score": f"{result.get('total_score',0)}/{result.get('max_score','?')}",
                    "Grade": f"{GRADE_COLOR.get(grade,'')} {grade}",
                    "%": f"{result.get('percentage',0):.1f}%",
                })
                live_tbl.dataframe(live_rows, use_container_width=True, hide_index=True)
                progress.progress(idx / len(submissions))
                if idx < len(submissions): time.sleep(0.2)

            combined = output_dir / "all_results.json"
            combined.write_text(json.dumps(all_results, indent=2))
            st.session_state.update({
                "last_results":    all_results,
                "assignment_name": assignment_name,
                "output_dir":      str(output_dir),
            })
            st.success(f"✓ Done — {len(all_results)} students graded")

            dc1, dc2 = st.columns(2)
            with dc1:
                st.download_button("⬇ Download JSON", data=combined.read_bytes(),
                                   file_name="all_results.json", mime="application/json")
            with dc2:
                buf = io.StringIO()
                csv.DictWriter(buf, fieldnames=list(live_rows[0])).writeheader()
                csv.DictWriter(buf, fieldnames=list(live_rows[0])).writerows(live_rows)
                st.download_button("⬇ Download CSV", data=buf.getvalue(),
                                   file_name="grading_summary.csv", mime="text/csv")


# ═══════════════════════════════════════════════════
# TAB 2 — RESULTS
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
        max_score = results[0].get("max_score", 20)
        scores = [r.get("total_score", 0) for r in results]
        pcts   = [r.get("percentage",  0) for r in results]
        grades = [r.get("letter_grade") or letter_grade(p) for r, p in zip(results, pcts)]

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
                               file_name="all_results.json", mime="application/json")
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
                               file_name="grading_summary.csv", mime="text/csv")

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

                    st.success(f"✓ {r['student_id']} updated — {new_total}/{max_score} ({new_grade})")
                    st.rerun()


# ═══════════════════════════════════════════════════
# TAB 3 — COMPARISON
# ═══════════════════════════════════════════════════
with tab3:
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
            st.subheader("Cost Comparison")
            co1, co2 = st.columns(2)
            co1.metric(fl_label, f"~${n*0.01:.2f}", "~$0.01 per student")
            co2.metric(ll_label, "$0.00", "Free — HF serverless")
