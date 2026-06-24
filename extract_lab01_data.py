from pathlib import Path
import json

from document_reader import read_document


SOURCE_DIR = Path("lab01_data/source_files")
OUTPUT_DIR = Path("lab01_data/extracted")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_files():
    guide_path = SOURCE_DIR / "CAI3801_Lab01_StepByStep_Guide.pdf"
    template_path = SOURCE_DIR / "CAI3801_Lab01_Student_Template.docx"

    guide_text = read_document(str(guide_path))
    template_text = read_document(str(template_path))

    extracted = {
        "assignment_name": "CAI 3801 Lab 01",
        "guide_text": guide_text,
        "template_text": template_text,
        "rubric": {
            "total_points": 20,
            "criteria": [
                {"name": "Context", "max_points": 4},
                {"name": "Understand table", "max_points": 5},
                {"name": "Evidence checks", "max_points": 6},
                {"name": "Memo quality", "max_points": 4},
                {"name": "AI Use Note", "max_points": 1}
            ]
        }
    }

    output_path = OUTPUT_DIR / "lab01_assignment_context.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(extracted, f, indent=2)

    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    extract_files()