# Methodology

This project is designed as a transparent local baseline for Bangla tax retrieval-augmented generation experiments.

## Research Framing

The repository focuses on grounded question answering over regulatory and tax documents where:

- temporal validity matters
- authority level matters
- exact section references matter
- unsupported answers are unacceptable

## Method

1. Parse source PDFs into structured page records.
2. Normalize metadata while preserving original Bangla text.
3. Chunk the document into retrieval-ready units.
4. Run sparse, dense, or hybrid retrieval.
5. Build a compact evidence pack from top-ranked chunks.
6. Generate answers only from evidence and require sentence-level citations.
7. Abstain when evidence is missing, weak, or unresolved.

## Design Principles

- Retrieval-first
  Retrieval quality is treated as a first-order research variable.
- Grounded generation
  Generation is constrained to provided evidence rather than open-ended completion.
- Transparent heuristics
  Ranking boosts, abstention gates, and confidence scores are intentionally interpretable.
- Local reproducibility
  Core experiments run without external APIs by default.

## Evaluation Philosophy

The current evaluation layer is intentionally lightweight, but it is structured so later experiments can compare:

- retrieval mode
- top-k settings
- evidence pack size
- abstention thresholds
- generation on vs off
