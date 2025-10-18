# /tests/test_filters.py
# Quick local tester for your filtering logic (no web requests, no timing).
# Paste example listings into SAMPLE below as dicts with title/description.

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from src.core.utils import (
    is_target_vehicle,
    annotate_tags,
    is_diesel,
    has_cummins,
    is_heavy_duty_model,
    is_specialty_body,
)

# === Paste your examples here ===
SAMPLE = [
    {
        "title": "2007 Ford F-750",
        "description": "2007 Ford F-750 CONVENTIONAL CAB, 7.2L L6 DIESEL. RUNS AND DRIVES AS IT SHOULD. NO KNOWN MECHANICAL ISSUES. ENGINE HOURS UNKNOWN",
    },
    # Add more cases you find on the site...
    # { "title": "...", "description": "..." },
]

def row_text(r: dict) -> str:
    return ((r.get("title") or "") + " " + (r.get("description") or "")).lower()

def explain(text: str) -> dict:
    return {
        "diesel": is_diesel(text),
        "cummins": has_cummins(text),
        "hd_model": is_heavy_duty_model(text),
        "specialty_body": is_specialty_body(text),
        "target_match": is_target_vehicle(text),
        "tags": annotate_tags(text),
    }

def main():
    for i, r in enumerate(SAMPLE, 1):
        t = row_text(r)
        verdict = explain(t)
        print("-" * 70)
        print(f"Case {i}")
        print("TITLE:", r.get("title"))
        print("DESC :", r.get("description"))
        print("=> diesel        :", verdict["diesel"])
        print("=> cummins       :", verdict["cummins"])
        print("=> hd_model      :", verdict["hd_model"])
        print("=> specialty     :", verdict["specialty_body"])
        print("=> TARGET MATCH? :", verdict["target_match"])
        print("=> tags          :", verdict["tags"])

if __name__ == "__main__":
    main()
