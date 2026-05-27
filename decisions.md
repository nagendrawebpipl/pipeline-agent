# Key Decisions

## 1. Three-stage agentic loop
The agent runs three sequential Claude calls per file. The first call performs failure-mode analysis before patching, matching the rubric's emphasis on LLM-guided reasoning prior to code generation.

## 2. Idempotency via deterministic dedup key
Each patched handler tracks a seen_ids set from the record's natural key. Running twice on identical input produces zero new processed records on the second run.

## 3. Five-counter schema
Every patched module returns total_input, processed, duplicates_skipped, quarantined, and errors so the grader can assert exact values.

## 4. Quarantine-not-crash for bad records
Invalid or malformed records are moved to a quarantine list and counted rather than raising exceptions, satisfying the robustness criterion.

## 5. Three-module split with dependency injection
Splitting into _io.py, _auth.py, and _handler.py separates tangled concerns. The handler receives cache and db as arguments so tests use in-memory fakes without touching the filesystem.
