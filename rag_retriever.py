"""
rag_retriever.py
----------------
RAG retrieval for rubric-calibrated grading — two modes:

  keyword  (default) : scores paragraphs by rubric keyword overlap.
                       Fast, no dependencies, works offline.

  semantic           : scores paragraphs by cosine similarity between
                       sentence embeddings (all-MiniLM-L6-v2, runs locally).
                       Catches vocabulary variation keyword mode misses —
                       e.g. "demonstrates understanding" matches "comprehends
                       the concept" even with no shared keywords.
                       Requires: pip install sentence-transformers

Switch mode in calibrated_grader.py via --rag-mode semantic.
"""

import re
from typing import List, Dict

# Semantic RAG — lazy-loaded on first use to avoid import cost when unused
_embed_model = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            print("  Loading sentence-transformer model (first run only)...")
            _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for --rag-mode semantic.\n"
                "Install it with: pip install sentence-transformers"
            )
    return _embed_model


# Rubric definition for CAI 3801 Lab 01
# Each criterion lists:
#   keywords     — terms strongly associated with this section of a submission
#   section_hints — section headers or labels students typically use
#   description  — human-readable summary (injected into the prompt)
LAB01_CRITERIA: List[Dict] = [
    {
        "name": "Context",
        "max_points": 4,
        "description": "Role, Goal, Audience, Constraints fields",
        "keywords": [
            "role", "goal", "audience", "constraint", "analyst", "owner",
            "decision", "purpose", "who", "why", "client", "stakeholder",
        ],
        "section_hints": ["context", "part 1", "section 1", "1."],
    },
    {
        "name": "Understand table",
        "max_points": 5,
        "description": "10-row review labeling table (Sentiment / Theme / Priority / Evidence)",
        "keywords": [
            "sentiment", "theme", "priority", "evidence", "review",
            "positive", "negative", "neutral", "high", "med", "low",
            "table", "label", "classification",
        ],
        "section_hints": ["understand", "table", "part 2", "section 2", "2.", "review table", "labeling"],
    },
    {
        "name": "Evidence checks",
        "max_points": 6,
        "description": "Revenue % calculation, Data A/B drivers, linked evidence bullets",
        "keywords": [
            "revenue", "percent", "%", "decline", "driver", "formula",
            "average", "ticket", "discount", "calculation", "data a",
            "data b", "8568", "7254", "increase", "decrease", "link",
        ],
        "section_hints": ["evidence", "calculation", "part 3", "section 3", "3.", "data a", "data b", "check"],
    },
    {
        "name": "Memo quality",
        "max_points": 4,
        "description": "Situation, What the data suggests, Recommendation, Owner + next step",
        "keywords": [
            "situation", "recommendation", "suggest", "memo", "summary",
            "next step", "action", "week", "bayside", "data shows",
            "primary", "backup", "executive",
        ],
        "section_hints": ["memo", "part 4", "section 4", "4.", "executive summary", "situation"],
    },
    {
        "name": "AI Use Note",
        "max_points": 1,
        "description": "AI prompts used, changes made to output, limitations/risks identified",
        "keywords": [
            "ai", "chatgpt", "prompt", "claude", "limitation", "risk",
            "generated", "tool", "llm", "gpt", "artificial intelligence",
            "language model", "changes made",
        ],
        "section_hints": ["ai use", "ai note", "part 5", "section 5", "5.", "disclosure", "artificial intelligence"],
    },
]


def split_into_chunks(text: str, min_length: int = 30) -> List[str]:
    """
    Split submission text into paragraph-level chunks.
    Chunks shorter than min_length characters are dropped.
    """
    raw = re.split(r'\n{2,}', text)
    return [c.strip() for c in raw if len(c.strip()) >= min_length]


def _score_chunk(chunk: str, keywords: List[str], section_hints: List[str]) -> float:
    """
    Score a single chunk's relevance to a criterion.
    Section-header matches get a 2x bonus.
    Score is normalized by sqrt(word count) to avoid length bias.
    """
    lower = chunk.lower()
    keyword_hits = sum(lower.count(kw) for kw in keywords)
    hint_bonus   = 2.0 * sum(1 for hint in section_hints if hint in lower)
    word_count   = max(1, len(chunk.split()))
    return (keyword_hits + hint_bonus) / (word_count ** 0.5)


def get_relevant_chunks(text: str, criterion: Dict, top_n: int = 3) -> List[str]:
    """
    Return the top_n chunks most relevant to a rubric criterion.
    Falls back to the first chunk(s) if nothing scores above zero.
    """
    chunks = split_into_chunks(text)
    if not chunks:
        return [text[:2000]]

    scored = sorted(
        [(c, _score_chunk(c, criterion["keywords"], criterion["section_hints"])) for c in chunks],
        key=lambda x: x[1],
        reverse=True,
    )

    top = [chunk for chunk, score in scored[:top_n] if score > 0]
    if not top:
        top = [chunk for chunk, _ in scored[:top_n]]

    return top


def build_rag_evidence(text: str, criteria: List[Dict] = None, top_n: int = 3) -> str:
    """
    Build a structured evidence block using keyword-based retrieval (default).

    Each criterion section contains only the most relevant anonymized
    chunks from the submission — not the full document.

    Args:
        text:     Anonymized submission text.
        criteria: Rubric criteria list (defaults to LAB01_CRITERIA).
        top_n:    Number of evidence chunks to retrieve per criterion.

    Returns:
        Formatted string ready to embed in a grading prompt.
    """
    if criteria is None:
        criteria = LAB01_CRITERIA

    sections = []
    for c in criteria:
        chunks = get_relevant_chunks(text, c, top_n=top_n)
        evidence = "\n---\n".join(chunks)
        sections.append(
            f"[CRITERION: {c['name']} | max {c['max_points']} pts | {c['description']}]\n"
            f"{evidence}"
        )

    return "\n\n".join(sections)


def build_rag_evidence_semantic(text: str, criteria: List[Dict] = None, top_n: int = 3) -> str:
    """
    Build a structured evidence block using semantic embedding retrieval.

    Uses cosine similarity between sentence embeddings to find relevant
    paragraphs — catches vocabulary variation that keyword matching misses.
    Model: all-MiniLM-L6-v2 (80MB, runs fully locally, no API cost).

    Args:
        text:     Anonymized submission text.
        criteria: Rubric criteria list (defaults to LAB01_CRITERIA).
        top_n:    Number of evidence chunks to retrieve per criterion.

    Returns:
        Formatted string ready to embed in a grading prompt.
    """
    import numpy as np

    if criteria is None:
        criteria = LAB01_CRITERIA

    model = _get_embed_model()
    chunks = split_into_chunks(text)
    if not chunks:
        return "(no evidence)"

    # Encode all paragraphs once — reuse across all criteria
    para_embeddings = model.encode(chunks, show_progress_bar=False)

    sections = []
    for c in criteria:
        # Query = criterion name + description + keywords
        query = (
            f"{c['name']} {c.get('description', '')} "
            + " ".join(c.get("keywords", []))
        )
        q_emb = model.encode([query], show_progress_bar=False)[0]

        # Cosine similarity for each paragraph
        norms = np.linalg.norm(para_embeddings, axis=1) * np.linalg.norm(q_emb)
        scores = np.dot(para_embeddings, q_emb) / np.where(norms == 0, 1, norms)

        top_indices = scores.argsort()[::-1][:top_n]
        top_chunks = [chunks[i] for i in top_indices]
        evidence = "\n---\n".join(top_chunks)

        sections.append(
            f"[CRITERION: {c['name']} | max {c['max_points']} pts | {c['description']}]\n"
            f"{evidence}"
        )

    return "\n\n".join(sections)
