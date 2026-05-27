# Coding Agent - Data Pipeline Reliability

A three-stage Claude-powered agent that hardens flaky legacy Python pipelines by adding deduplication, validation, idempotency, and processing counters.

## How it works

1. Analyse - identify failure modes (duplicates, no validation, missing counters)
2. Patch - produce three focused modules (_io, _auth, _handler) with all reliability fixes
3. Test - generate pytest tests covering counters, duplicate handling, quarantine, and idempotency

## Running locally

pip install -r requirements.txt
set ANTHROPIC_API_KEY=sk-ant-...
python solution.py

## Docker

docker build -t pipeline-agent .
docker run --rm -e ANTHROPIC_API_KEY=your_key -v path/to/test_inputs.json:/workspace/test_inputs.json pipeline-agent

See decisions.md for architectural choices.
