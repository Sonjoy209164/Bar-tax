# OCR-Uncertainty-Aware Chunking and Retrieval

This note captures the core idea, theory, and research framing for an A*-oriented novelty direction for `bangla-tax-rag`.

## 1. Core Idea

Most retrieval systems assume that extracted document text is trustworthy once it becomes searchable text. That assumption is often false for low-resource legal and tax PDFs, especially when:

- OCR quality is uneven
- Bangla glyphs are corrupted
- headings are broken
- tables are split badly
- subsection markers are partially lost

The main idea is:

**a chunk should be ranked not only by relevance, but also by how reliable its OCR-derived text is as legal evidence.**

## 2. Motivation

In legal and tax question answering, OCR noise is not just a surface-level problem. A small recognition error can change:

- section identity
- tax rate
- authority reference
- tax-year interpretation
- whether a clause applies at all

That means OCR quality directly affects downstream legal correctness.

So instead of treating OCR as a one-time preprocessing step, we treat it as a source of uncertainty that should influence:

- chunking
- retrieval
- evidence selection
- abstention

## 3. Main Hypothesis

> In low-resource legal document QA, OCR uncertainty should be modeled as part of evidence quality rather than treated as a separate preprocessing artifact.

If this is true, then a retrieval system that accounts for OCR uncertainty should:

- select cleaner evidence more often
- reduce wrong-section retrieval
- improve citation faithfulness
- abstain more appropriately when all evidence is unreliable

## 4. Conceptual Framework

Each chunk has at least two properties:

1. `relevance`
2. `reliability`

Traditional retrieval mostly optimizes relevance.

This method optimizes both:

```text
Evidence Utility = Relevance + Legal Validity - Uncertainty Penalty
```

or conceptually:

```text
P(useful evidence | query, chunk) depends on:
- semantic relevance
- structural reliability
- OCR confidence
- authority validity
- temporal validity
```

## 5. Chunking Under Uncertainty

OCR uncertainty affects chunking first.

When page text is noisy, a chunker should not behave as if structure is perfectly known.

### Standard chunking assumption

- headings are reliable
- boundaries are visible
- section markers are readable

### OCR-aware chunking assumption

- some boundaries are uncertain
- some headings are partially corrupted
- some chunks should be marked low-confidence
- chunk refinement should be more conservative on noisy pages

### What OCR-aware chunking could do

- assign a `chunk_quality_score`
- detect noisy heading markers
- avoid overconfident section assignment
- merge small broken fragments only when confidence supports it
- trigger selective repair on ambiguous pages

## 6. Retrieval Under Uncertainty

The retrieval side uses OCR uncertainty as a ranking factor.

### Problem

A chunk may match the query strongly because of keyword overlap, but still be unreliable as legal evidence.

Example:

- Chunk A: strong lexical match, severe OCR corruption
- Chunk B: slightly weaker lexical match, structurally clean, correct section marker

Standard retrieval may prefer A.  
OCR-uncertainty-aware retrieval should often prefer B.

### Retrieval principle

The system should prefer:

- relevant chunks
- structurally coherent chunks
- temporally valid chunks
- legally authoritative chunks
- OCR-reliable chunks

## 7. Types of Uncertainty Signals

OCR uncertainty can be estimated using chunk-level features such as:

- OCR engine confidence, if available
- corrupted character ratio
- unusual digit or symbol density
- broken Bangla token ratio
- language-model perplexity
- section marker consistency
- heading parse confidence
- line fragmentation severity
- table-row integrity
- metadata consistency across nearby chunks

These can be grouped into:

- `text_quality`
- `structure_quality`
- `metadata_confidence`

## 8. Proposed Scoring View

A simple scoring view could be:

```text
final_score =
  alpha * retrieval_score
  + beta * section_match_score
  + gamma * authority_time_validity
  + delta * structure_confidence
  - lambda * ocr_uncertainty
```

Where:

- `retrieval_score` comes from sparse, dense, or hybrid retrieval
- `section_match_score` rewards correct heading or subsection alignment
- `authority_time_validity` rewards legal validity
- `structure_confidence` rewards coherent chunk boundaries
- `ocr_uncertainty` penalizes low-trust text

This can begin as a transparent heuristic model and later become a learned reranking model.

## 9. Why This Is Research-Worthy

This direction is stronger than “better OCR preprocessing” because it changes the retrieval problem itself.

The claim is not:

- OCR matters

The stronger claim is:

- **evidence reliability under OCR noise is part of the legal retrieval problem**

That makes this contribution relevant beyond Bangladesh tax PDFs, especially for:

- low-resource legal archives
- scanned regulations
- multilingual government documents
- OCR-heavy court or gazette corpora

## 10. Novelty Angle

The novelty comes from combining:

- OCR-aware ingestion
- uncertainty-aware chunking
- reliability-aware retrieval
- legal validity constraints
- grounded abstention

That combination is more publishable than just building a legal chatbot.

## 11. Suggested Method Design

### Stage 1: Base parsing

- extract text from PDF
- optionally apply OCR first

### Stage 2: Uncertainty estimation

- assign a confidence profile to each page or chunk

### Stage 3: OCR-aware chunking

- split or merge with uncertainty-aware rules
- preserve chunk-level quality metadata

### Stage 4: Retrieval

- retrieve using sparse, dense, or hybrid search
- rerank with OCR uncertainty and legal validity features

### Stage 5: Evidence selection

- filter unreliable chunks
- retain high-confidence, legally valid evidence
- abstain when all evidence is too uncertain

## 12. Suggested Experiments

### Main comparison

- direct extraction without OCR
- OCR-first extraction
- OCR-first + uncertainty-aware chunking
- OCR-first + uncertainty-aware retrieval
- OCR-first + uncertainty-aware chunking + retrieval

### Retrieval settings

- sparse
- hybrid
- hybrid + authority/time-aware reranking
- hybrid + OCR uncertainty

### Evaluation targets

- evidence retrieval quality
- section accuracy
- citation correctness
- answer faithfulness
- abstention correctness

## 13. Suggested Metrics

### Retrieval

- Recall@k
- MRR
- nDCG
- evidence precision

### Generation

- citation support rate
- unsupported claim rate
- abstention precision and recall

### OCR / Chunking

- heading recovery accuracy
- chunk purity
- section-boundary quality
- corruption sensitivity

## 14. Strong Contribution Statement

You can frame the contribution like this:

> We propose an OCR-uncertainty-aware retrieval framework for low-resource legal and tax question answering, where OCR reliability is modeled as part of chunk quality and evidence selection rather than treated solely as a preprocessing artifact.

## 15. Suggested Paper Positioning

This idea fits well with a paper framed around:

- low-resource legal RAG
- Bangla-English legal/tax QA
- OCR-aware evidence retrieval
- grounded generation under noisy document extraction

## 16. What Is Already Present In This Repo

Partially present:

- OCR-first ingestion
- chunk cleaning heuristics
- authority-aware reranking
- tax-year-aware reranking
- abstention

Not fully implemented yet:

- explicit OCR confidence modeling
- uncertainty-aware chunk scoring
- uncertainty-aware retrieval objective
- rigorous benchmark proving gains

## 17. Next Practical Step

To make this idea concrete in the repository, the next implementation step would be:

1. add chunk-level OCR or text-quality confidence scores
2. propagate them into chunk metadata
3. inject them into sparse and hybrid post-ranking
4. evaluate against a gold dataset

That would turn the idea from theory into a publishable method direction.
