"""Benchmark NL->MQL translation across models. For each scholar question and each
model: translate with the curriculum prompt, validate, run the MQL against the DB,
and compare the count to the pinned expected_count. Prints a per-model table with
count-match accuracy and exact cost/query. Runs in CI (needs Emdros + the BHSA DB
+ ANTHROPIC_API_KEY). NOT a pytest test."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from shebanq_mcp.feature_reference import FeatureReference  # noqa: E402
from shebanq_mcp.translate import build_prompt, _strip_fences  # noqa: E402
from shebanq_mcp.validator import validate_mql  # noqa: E402
from shebanq_mcp.runner import run_query  # noqa: E402

MODELS = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"]
PRICING = {  # $/1M (input, output)
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
DB = os.environ.get("BHSA_SQLITE", "data/bhsa.sqlite3")
FIX = Path(__file__).parent.parent / "tests" / "fixtures" / "scholar_questions.json"


def cost(model: str, in_tok: int, out_tok: int) -> float:
    pin, pout = PRICING[model]
    return in_tok / 1e6 * pin + out_tok / 1e6 * pout


def score(mql: str, expected: int, ref) -> tuple[str, int | None]:
    """Verdict for one generated query: 'ok' | 'wrong:N' | 'invalid' | 'error:..'"""
    if not validate_mql(mql, ref).ok:
        return ("invalid", None)
    try:
        c = run_query(mql, DB, limit=1).count
    except Exception as exc:  # noqa: BLE001 - report, keep going
        return (f"error:{exc}", None)
    return ("ok" if c == expected else f"wrong:{c}", c)


def main() -> None:
    import anthropic
    ref = FeatureReference.load()
    system = build_prompt(ref)
    questions = json.loads(FIX.read_text(encoding="utf-8"))["questions"]
    client = anthropic.Anthropic()
    for model in MODELS:
        correct = 0
        total_cost = 0.0
        rows = []
        for q in questions:
            msg = client.messages.create(
                model=model, max_tokens=1024, system=system,
                messages=[{"role": "user", "content": q["question"]}])
            mql = _strip_fences(msg.content[0].text)
            verdict, _ = score(mql, q["expected_count"], ref)
            total_cost += cost(model, msg.usage.input_tokens, msg.usage.output_tokens)
            correct += verdict == "ok"
            rows.append((q["name"], verdict))
        n = len(questions)
        print(f"\n=== {model}: {correct}/{n} correct | ${total_cost / n:.4f}/query ===")
        for name, verdict in rows:
            print(f"  {'PASS' if verdict == 'ok' else 'FAIL'}  {name}: {verdict}")
    print("\nMODELS:", ", ".join(MODELS))


if __name__ == "__main__":
    main()
