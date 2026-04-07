# Experiments

This project is ready for small local experiments and paper-style baselines.

## Suggested Experiment Matrix

- Retrieval mode
  `sparse`, `dense`, `hybrid`
- Top-k retrieval
  `3`, `5`, `10`
- Final evidence size
  `2`, `3`, `5`
- Generation mode
  retrieval only vs grounded generation
- Abstention threshold
  `0.5`, `0.75`, `1.0`

## Core Metrics

- Exact match placeholder metric
- Retrieval hit inspection by section and tax year
- Conflict frequency
- Abstention frequency
- Citation coverage

## Sample Local Workflow

1. Build indexes from `data/processed/sample_chunks.jsonl`
2. Run sparse and hybrid demo queries
3. Evaluate against `data/processed/sample_eval.jsonl`
4. Record metrics summaries under `results/`

## Notes For Paper Experiments

- Keep the chunking strategy fixed while comparing retrieval modes.
- Record the exact config used for each run.
- Inspect failure cases separately for:
  weak retrieval
  unresolved conflicts
  abstention triggers
  citation verification failures
