"""Print the real count for every fixture query. Runs in CI (needs Emdros +
the BHSA db); the printed lines are the source for pinning expected_count."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from shebanq_mcp.runner import run_query  # noqa: E402

DB = os.environ.get("BHSA_SQLITE", "data/bhsa.sqlite3")
FIX = Path(__file__).parent.parent / "tests" / "fixtures"

for fname, key in (("mql_constructs.json", "constructs"),
                   ("scholar_questions.json", "questions")):
    data = json.loads((FIX / fname).read_text(encoding="utf-8"))
    for case in data[key]:
        try:
            r = run_query(case["mql"], DB, limit=1)
            print(f"PINCOUNT {fname}:{case['name']} count={r.count}")
        except Exception as exc:  # noqa: BLE001 - report, keep going
            print(f"PINCOUNT {fname}:{case['name']} ERROR={exc}")
