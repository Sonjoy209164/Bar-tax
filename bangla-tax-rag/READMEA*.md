# A* Roadmap For `bangla-tax-rag`

This document is a research roadmap for turning `bangla-tax-rag` from a strong local legal/tax RAG system into an A*-level research project.

It is not a claim that the current repository is already A*-ready. It is a plan for what must be added, validated, and argued to make the work competitive at a top-tier venue.

## 1. Hard Truth

As it stands, the repository is a strong:

- system prototype
- reproducible research scaffold
- legal/tax RAG baseline platform
- OCR-aware document QA engineering project

That is valuable, but A* papers usually require more than a solid system. They typically need:

- a new benchmark or dataset
- a new method
- a new evaluation framework
- or a new insight that generalizes beyond one application setting

For this project, the most realistic A*-oriented path is:

1. build a benchmark
2. add one serious methodological contribution
3. run rigorous ablations and failure analysis

## 2. Best A* Direction

The strongest direction for this repository is:

**OCR-aware legal RAG for low-resource Bangla-English tax and legal documents**

This is stronger than:

- “we built a tax chatbot”
- “we used DeepSeek for Bangla QA”
- “we combined BM25 and RAG for tax PDFs”

The contribution becomes much more compelling if the paper is framed around:

- noisy OCRed legal PDFs
- low-resource Bangla-English legal retrieval
- evidence-grounded answer generation
- abstention and citation faithfulness

## 3. Best Novelty Options

You do not need five novelties. You need one main novelty and one supporting novelty.

### Option A: OCR-Uncertainty-Aware Legal RAG

This is one of the strongest options.

Core idea:

- OCR errors damage chunking, retrieval, and answer quality
- legal RAG systems usually assume clean text
- low-resource Bangla legal/tax PDFs often violate that assumption

Possible novelty:

- OCR confidence-aware chunk ranking
- OCR noise-aware retrieval scoring
- abstention when evidence quality is too corrupted
- OCR-aware evidence selection

Why this is strong:

- important beyond Bangladesh
- methodologically meaningful
- directly tied to a real failure mode

### Option B: LLM-Assisted Structure Recovery for Legal PDFs

This is also strong if you do it carefully.

Core idea:

- PDF extraction loses legal structure
- chunk boundaries become noisy
- subsection hierarchy is often corrupted

Possible novelty:

- heuristic parser first
- selective LLM refinement only for ambiguous pages
- section/subsection recovery
- legal clause-aware chunk repair

Why this is strong:

- chunking is underexplored compared to downstream generation
- legal document structure matters deeply
- easy to ablate against heuristic chunking

### Option C: Authority- and Time-Aware Legal Retrieval

This is a legal-domain-specific method contribution.

Core idea:

- legal/tax answer correctness depends on more than lexical similarity
- source authority and tax-year validity matter
- retrieval should model those constraints directly

Possible novelty:

- authority-aware reranking
- tax-year-aware evidence selection
- conflict-aware legal evidence packing
- abstention when supporting evidence is temporally or hierarchically invalid

Why this is strong:

- domain-grounded
- generalizable to regulations and statutes
- easy to evaluate rigorously

### Option D: Benchmark Contribution

This is probably the most reliable way to make the work publishable.

Core idea:

- create a benchmark for Bangla-English legal/tax QA
- include OCRed and clean variants
- include evidence labels and abstention labels

Possible novelty:

- first benchmark for this specific setting
- paired OCR/no-OCR legal QA
- question types that reflect legal use cases

Why this is strong:

- benchmarks are highly valued in low-resource NLP
- makes the project useful beyond one paper

## 4. Recommended Contribution Combination

The best combination for this repository is:

### Main contribution

**A benchmark for OCR-aware Bangla-English legal/tax QA**

### Supporting method contribution

**OCR-aware chunking and retrieval with authority- and tax-year-aware evidence selection**

This combination is stronger than a pure application paper because it has:

- a resource contribution
- a method contribution
- a realistic and socially relevant domain

## 5. What Dataset You Need

For an A*-oriented paper, the dataset should not be tiny or purely synthetic.

### Minimum useful target

- 300 to 500 gold questions for an early serious paper

### Stronger target

- 800 to 1500 questions across multiple documents

### Include both

- Bangla tax circulars
- English tax/legal acts

### Important labels

Each example should ideally include:

- question text
- question type
- gold answer
- expected supporting chunk ids
- expected section or subsection
- tax year if applicable
- authority preference if applicable
- whether the system should abstain

### Key question types

- definition
- rate lookup
- amendment
- procedure
- example-based
- calculation
- comparison
- authority conflict
- abstention-required

## 6. What Method You Need

For A*, the method should be more than hand-tuned heuristics, even if heuristics remain part of the system.

### Good method direction 1

**Selective LLM chunk refinement**

- heuristic parser proposes chunk boundaries
- uncertainty detector flags bad pages
- LLM refines only ambiguous sections
- output remains structured and auditable

### Good method direction 2

**OCR-uncertainty-aware retrieval**

- estimate text corruption severity per chunk
- adjust chunk ranking based on OCR reliability
- fuse semantic relevance with structural reliability

### Good method direction 3

**Constraint-aware evidence selection**

- rank by lexical or semantic relevance
- then enforce or softly prefer:
  - authority validity
  - tax-year validity
  - section match
  - evidence consistency

## 7. What Baselines You Need

You need stronger baselines than the current repo if you want A* competitiveness.

At minimum:

- BM25 sparse baseline
- current hybrid baseline
- multilingual embedding retriever
- cross-encoder or reranker baseline
- retrieval-only baseline
- generation-enabled baseline

For OCR/chunking work, also compare:

- direct extraction without OCR
- OCR-first extraction
- OCR + heuristic chunking
- OCR + heuristic + LLM refinement

## 8. What Experiments You Need

### Core ablations

- sparse vs dense vs hybrid
- chunking strategy
- OCR on vs OCR off
- LLM chunk refinement on vs off
- generation on vs off
- authority-aware reranking on vs off
- tax-year-aware reranking on vs off
- abstention threshold variation

### Required analysis

- retrieval accuracy
- evidence accuracy
- citation correctness
- answer faithfulness
- abstention precision and recall
- OCR robustness

## 9. What Metrics You Need

For A*, do not rely only on loose qualitative claims.

### Retrieval

- Recall@k
- MRR
- nDCG
- evidence precision

### Generation

- answer exact match or semantic match
- citation support rate
- unsupported claim rate
- abstention correctness

### OCR / chunking

- section boundary quality
- chunk purity
- heading recovery accuracy
- OCR corruption sensitivity

## 10. What Error Analysis You Need

A* papers usually need careful failure analysis.

Use categories like:

- OCR failure
- parser failure
- chunk boundary failure
- wrong section retrieval
- temporal mismatch
- authority mismatch
- conflicting evidence
- unsupported generation
- over-abstention
- under-abstention

## 11. Strong Paper Framing Options

Here are realistic A*-style framing directions.

### Framing 1

**OCR-Aware Legal RAG for Low-Resource Bangla-English Tax Documents**

### Framing 2

**Structure Recovery and Evidence-Grounded QA for Noisy Legal PDFs**

### Framing 3

**Temporal- and Authority-Aware Retrieval for Legal Question Answering**

### Framing 4

**A Benchmark and Baselines for Bangla-English Tax and Legal QA over OCRed PDFs**

## 12. What Is Not Enough

These alone are usually not enough for A*:

- Streamlit UI
- FastAPI integration
- using DeepSeek through Ollama
- BM25 plus heuristic hybrid retrieval
- a small synthetic dataset
- a domain demo without rigorous evaluation

## 13. Most Realistic A* Strategy

If the goal is genuine A* competitiveness, the best practical route is:

1. finish and freeze the ingestion and chunking pipeline
2. create a meaningful gold benchmark
3. replace placeholder dense retrieval with a real multilingual retriever
4. add one serious method contribution
5. run strong ablations
6. write a careful failure-analysis section

## 14. Suggested Research Plan

### Phase 1: Resource

- build corpus
- OCR documents
- finalize chunking
- annotate benchmark

### Phase 2: Baselines

- strong sparse baseline
- real dense baseline
- hybrid baseline

### Phase 3: Method

- OCR-aware chunk refinement or OCR-aware retrieval
- authority/time-aware evidence selection

### Phase 4: Evaluation

- benchmark splits
- ablations
- citation and abstention evaluation
- human review of difficult cases

## 15. Suggested Gap Statement

You can adapt this statement directly:

> Existing legal and regulatory RAG systems generally assume cleaner source text or do not jointly study OCR quality, chunk structure recovery, retrieval validity, citation-grounded generation, and abstention in low-resource Bangla-English legal and tax documents. We address this gap by introducing a benchmark and an OCR-aware retrieval pipeline for evidence-grounded question answering over noisy legal PDFs.

## 16. Suggested Contributions Section

A strong contribution section could look like:

1. We introduce a benchmark for Bangla-English tax and legal QA over OCRed and non-OCRed PDFs.
2. We propose an OCR-aware retrieval pipeline that improves evidence quality under noisy document extraction.
3. We study the interaction between chunk quality, hybrid retrieval, citation-grounded generation, and abstention.
4. We provide a reproducible local research framework for low-resource legal RAG.

## 17. Bottom Line

If you want this project to have a realistic A* path, the best move is not to add more app features. The best move is to turn it into:

- a benchmark
- a method
- a rigorous evaluation study

That is the combination that can make the work intellectually strong enough.
