"""
Compatibility entrypoint for platforms that expect src/streamlit_app.py.

The production BullsEye app lives at the repository root in app.py.
Run locally with:
    streamlit run app.py
"""

from pathlib import Path


ROOT_APP = Path(__file__).resolve().parents[1] / "app.py"
exec(compile(ROOT_APP.read_text(encoding="utf-8"), str(ROOT_APP), "exec"))
