"""
run_experiments.py
------------------
One script to run all pending experiments needed for publication.

Experiments:
  set5  — Semantic RAG vs keyword RAG (same model, Set 2 approach)
  hf    — HF Inference API model comparison (Qwen2.5-7B via HF, all 15 students)
  shots — Build calibrated few-shot examples from Set 2 results

Usage:
  python run_experiments.py --run set5  --anthropic-key sk-ant-...
  python run_experiments.py --run hf    --hf-token hf_...
  python run_experiments.py --run shots
  python run_experiments.py --run all   --hf-token hf_...
"""

import argparse, json
from pathlib import Path

INSTRUCTIONS = "lab01_data/source_files/CAI3801_Lab01_StepByStep_Guide.pdf"
CRITERIA_JSON = "lab01_data/source_files/lab01_criteria.json"
SUBMISSIONS   = "lab01_data/student_submissions/"
SET2_RESULTS  = "lab01_data/experiments/set2_results.json"


# ── Set 5: Semantic RAG ──────────────────────────────────────────────────────

def run_set5(api_key: str, provider: str = "anthropic", model: str = None):
    """Run Set 2 approach but with semantic RAG instead of keyword RAG."""
    model = model or ("claude-sonnet-4-6" if provider == "anthropic" else "gpt-4o-mini")
    print(f"\n=== SET 5: Semantic RAG Comparison ({provider} · {model}) ===")
    from document_reader import read_document, load_student_submissions
    from calibrated_grader import CalibratedGrader
    from few_shot_builder import build_examples_from_results, save_examples

    out_dir = Path("lab01_data/experiments/set5_semantic_rag")
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(CRITERIA_JSON) as f:
        criteria = json.load(f)

    instructions_text = read_document(INSTRUCTIONS)
    submissions = load_student_submissions(SUBMISSIONS)

    grader = CalibratedGrader(
        criteria=criteria,
        assignment_name="CAI 3801 Lab 01 — Set 5 Semantic RAG",
        model=model,
        provider=provider,
        api_key=api_key,
        rag_mode="semantic",
    )

    results = []
    for idx, sub in enumerate(submissions, 1):
        sid = f"Student_{idx:03d}"
        print(f"  [{idx:02d}/{len(submissions)}] {sid} ({sub['name']})...", end=" ", flush=True)
        try:
            result = grader.grade_submission(
                instructions_text=instructions_text,
                submission_text=sub["text"],
                student_id=sid,
                student_name=sub["name"],
            )
            (out_dir / f"{sid}.json").write_text(json.dumps(result, indent=2))
            results.append(result)
            print(f"{result.get('total_score',0)}/{result.get('max_score',20)}")
        except Exception as e:
            print(f"ERROR: {e}")

    combined = out_dir / "all_results.json"
    combined.write_text(json.dumps(results, indent=2))
    print(f"\nSet 5 done → {combined}")
    _compare_to_set2(results, "Set 5 — Semantic RAG")


# ── HF Model Comparison (all 15 students) ───────────────────────────────────

def run_hf_comparison(hf_token: str, model: str = "Qwen/Qwen2.5-7B-Instruct"):
    """Run Qwen2.5-7B via HF Inference API on all 15 students."""
    print(f"\n=== HF MODEL COMPARISON: {model} ===")
    from document_reader import read_document, load_student_submissions
    from calibrated_grader import CalibratedGrader

    out_dir = Path("lab01_data/experiments/hf_model_comparison")
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(CRITERIA_JSON) as f:
        criteria = json.load(f)

    instructions_text = read_document(INSTRUCTIONS)
    submissions = load_student_submissions(SUBMISSIONS)

    grader = CalibratedGrader(
        criteria=criteria,
        assignment_name="CAI 3801 Lab 01 — HF Qwen2.5-7B",
        model=model,
        provider="huggingface",
        api_key=hf_token,
        rag_mode="keyword",
    )

    results = []
    for idx, sub in enumerate(submissions, 1):
        sid = f"Student_{idx:03d}"
        print(f"  [{idx:02d}/{len(submissions)}] {sid} ({sub['name']})...", end=" ", flush=True)
        try:
            result = grader.grade_submission(
                instructions_text=instructions_text,
                submission_text=sub["text"],
                student_id=sid,
                student_name=sub["name"],
            )
            (out_dir / f"{sid}.json").write_text(json.dumps(result, indent=2))
            results.append(result)
            print(f"{result.get('total_score',0)}/{result.get('max_score',20)}")
        except Exception as e:
            print(f"ERROR: {e}")

    combined = out_dir / "all_results.json"
    combined.write_text(json.dumps(results, indent=2))
    print(f"\nHF comparison done → {combined}")
    _compare_to_set2(results, f"HF — {model}")


# ── Few-shot: build calibrated examples ─────────────────────────────────────

def build_few_shot():
    """Build calibrated few-shot examples from Set 2 results."""
    print("\n=== BUILDING CALIBRATED FEW-SHOT EXAMPLES ===")
    from few_shot_builder import build_examples_from_results, save_examples, summarize_examples

    with open(SET2_RESULTS) as f:
        results = json.load(f)

    # Build with n_per_band=1: one high, one medium, one low
    # This is the calibrated approach — not just A students
    examples = build_examples_from_results(results, n_per_band=1)
    out_path = "lab01_data/experiments/few_shot_examples_calibrated.json"
    save_examples(examples, out_path)
    print(summarize_examples(examples))
    print(f"\nSaved → {out_path}")
    print("Use with: --examples lab01_data/experiments/few_shot_examples_calibrated.json")


# ── Compare helper ───────────────────────────────────────────────────────────

def _compare_to_set2(new_results, label: str):
    """Quick comparison of new results against Set 2 baseline."""
    with open(SET2_RESULTS) as f:
        set2 = {r["student_id"]: r for r in json.load(f)}

    new_map = {r["student_id"]: r for r in new_results}
    common  = sorted(s for s in set2 if s in new_map)
    if not common:
        print("No common students to compare."); return

    print(f"\n── Comparison: Set 2 (Claude) vs {label} ──")
    print(f"  {'Student':<14} {'Set2':>6} {'New':>6} {'Diff':>6}")
    diffs = []
    for sid in common:
        s2 = set2[sid].get("total_score", 0)
        nw = new_map[sid].get("total_score", 0)
        d  = round(nw - s2, 1)
        diffs.append(d)
        print(f"  {sid:<14} {s2:>6.1f} {nw:>6.1f} {d:>+6.1f}")
    avg_gap = sum(diffs)/len(diffs)
    agree   = sum(1 for d in diffs if abs(d) <= 2)/len(diffs)*100
    print(f"\n  Avg gap vs Set 2 : {avg_gap:+.2f} pts")
    print(f"  Within ±2 pts   : {agree:.0f}%")
    print(f"  Students compared: {len(common)}")


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", choices=["set5","hf","shots","all"], required=True)
    parser.add_argument("--openai-key", default=None, help="OpenAI API key (optional for set5)")
    parser.add_argument("--anthropic-key", default=None, help="Anthropic API key (default provider for set5)")
    parser.add_argument("--set5-provider", default="anthropic", choices=["anthropic", "openai"],
                        help="Provider for Set 5. Use the same provider/model as Set 2 for a clean RAG comparison.")
    parser.add_argument("--hf-token",   default=None, help="HF token (for hf)")
    parser.add_argument("--model",      default=None, help="Override model name")
    args = parser.parse_args()

    import os
    from pathlib import Path

    # Load from .env if not provided
    env = Path(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    openai_key = args.openai_key or os.environ.get("OPENAI_API_KEY")
    anthropic_key = args.anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
    hf_token   = args.hf_token   or os.environ.get("HF_TOKEN")

    if args.run in ("set5", "all"):
        set5_key = anthropic_key if args.set5_provider == "anthropic" else openai_key
        if not set5_key:
            env_name = "ANTHROPIC_API_KEY" if args.set5_provider == "anthropic" else "OPENAI_API_KEY"
            print(f"ERROR: --{args.set5_provider}-key or {env_name} required for set5"); exit(1)
        run_set5(set5_key, provider=args.set5_provider, model=args.model)

    if args.run in ("hf", "all"):
        if not hf_token:
            print("ERROR: --hf-token or HF_TOKEN required for hf"); exit(1)
        run_hf_comparison(hf_token, model=args.model or "Qwen/Qwen2.5-7B-Instruct")

    if args.run in ("shots", "all"):
        build_few_shot()
