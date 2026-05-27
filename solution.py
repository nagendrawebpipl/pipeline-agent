#!/usr/bin/env python3
import json
import os
import re
import sys
import time
from pathlib import Path
import anthropic

TEST_INPUTS_PATH = Path(os.environ.get("TEST_INPUTS_PATH", "test_inputs.json"))
RESULTS_PATH     = Path(os.environ.get("RESULTS_PATH",     "results.json"))

ANALYSIS_PROMPT = (
    "You are a senior data-pipeline reliability engineer.\n"
    "Analyse the legacy Python pipeline below and list every reliability failure mode.\n"
    "Focus on: duplicate records, missing validation, no idempotency guard, absent processing counters, global mutable state, swallowed errors, unsafe file I/O.\n\n"
    "File: {filename}\nKnown issues: {issues}\nGoals: {goals}\n\nLegacy code:\n{code}\n\n"
    "Respond ONLY with a JSON object, no markdown fences:\n"
    '{{"failure_modes": ["<mode1>"], "dedup_key": "<field>", "validation_rules": ["<rule1>"]}}'
)

PATCH_PROMPT = (
    "You are an expert Python reliability engineer.\n"
    "Patch the legacy pipeline to fix ALL listed failure modes.\n"
    "MUST have: 1) Deduplication using {dedup_key}, track duplicates_skipped "
    "2) Validation: {validation_rules}, quarantine invalid, track quarantined "
    "3) Idempotency - running twice produces identical counters "
    "4) Counters: total_input, processed, duplicates_skipped, quarantined, errors "
    "5) Three modules: {stem}_io.py, {stem}_auth.py, {stem}_handler.py\n\n"
    "File: {filename}\nFailure modes:\n{failure_modes}\n\nLegacy code:\n{code}\n\n"
    "Respond ONLY with a JSON object, no markdown fences:\n"
    '{{"modules": [{{"filename": "{stem}_io.py", "code": "<src>"}}, {{"filename": "{stem}_auth.py", "code": "<src>"}}, {{"filename": "{stem}_handler.py", "code": "<src>"}}], '
    '"counters_schema": {{"total_input": "<int>", "processed": "<int>", "duplicates_skipped": "<int>", "quarantined": "<int>", "errors": "<int>"}}, '
    '"summary": "<one sentence>"}}'
)

TEST_PROMPT = (
    "You are a Python test engineer.\n"
    "Write pytest tests for {stem}_handler.py covering: correct processed count, duplicates_skipped > 0, quarantined > 0, idempotency, negative amounts quarantined, empty input returns zeros.\n"
    "Use only stdlib + pytest. Mock file I/O with tmp_path.\n\n"
    "Summary: {summary}\nCounters schema: {counters_schema}\n\n"
    "Respond ONLY with a JSON object, no markdown fences:\n"
    '{{"test_filename": "test_{stem}.py", "test_code": "<full pytest source>"}}'
)

def _call(client, prompt, retries=3):
    for attempt in range(retries):
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except (json.JSONDecodeError, anthropic.APIError) as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"Claude failed: {exc}") from exc

def stem_of(filename):
    base = Path(filename).stem
    return re.sub(r"_\d+$", "", base)

def process_item(client, item):
    filename = item["filename"]
    code     = item["legacy_code"]
    issues   = item["issues"]
    goals    = item["refactoring_goals"]
    stem     = stem_of(filename)

    analysis = _call(client, ANALYSIS_PROMPT.format(
        filename=filename, issues=", ".join(issues), goals=goals, code=code))
    failure_modes    = analysis.get("failure_modes", issues)
    dedup_key        = analysis.get("dedup_key", "id")
    validation_rules = analysis.get("validation_rules", ["record must not be None"])

    patch = _call(client, PATCH_PROMPT.format(
        filename=filename, stem=stem,
        failure_modes="\n".join(f"  - {m}" for m in failure_modes),
        dedup_key=dedup_key,
        validation_rules=", ".join(validation_rules),
        code=code))
    modules         = patch.get("modules", [])
    counters_schema = patch.get("counters_schema", {})
    summary         = patch.get("summary", "")

    tests = _call(client, TEST_PROMPT.format(
        stem=stem, summary=summary,
        counters_schema=json.dumps(counters_schema)))

    return {
        "id": item["id"],
        "output": {
            "original_filename": filename,
            "failure_modes_identified": failure_modes,
            "refactored_modules": modules,
            "counters_schema": counters_schema,
            "tests": {
                "filename": tests.get("test_filename", f"test_{stem}.py"),
                "code":     tests.get("test_code", ""),
            },
            "summary": summary,
            "issues_addressed": issues,
        },
    }

def main():
    if not TEST_INPUTS_PATH.exists():
        print(f"ERROR: {TEST_INPUTS_PATH} not found", file=sys.stderr)
        sys.exit(1)
    test_inputs = json.loads(TEST_INPUTS_PATH.read_text())
    client      = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    results     = []
    total       = len(test_inputs)
    for idx, item in enumerate(test_inputs, 1):
        print(f"[{idx}/{total}] Processing {item['filename']} ({item['id']}) ...")
        try:
            result = process_item(client, item)
            results.append(result)
            print(f"  Done - {len(result['output']['refactored_modules'])} modules + tests")
        except Exception as exc:
            print(f"  Error: {exc}", file=sys.stderr)
            results.append({
                "id": item["id"],
                "output": {
                    "original_filename": item["filename"],
                    "failure_modes_identified": [],
                    "refactored_modules": [],
                    "counters_schema": {},
                    "tests": {"filename": "", "code": ""},
                    "summary": f"ERROR: {exc}",
                    "issues_addressed": [],
                },
            })
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nDone - {len(results)} results written to {RESULTS_PATH}")

if __name__ == "__main__":
    main()

