# Related Work

This note summarizes representative work that is relevant to `bangla-tax-rag`. It is intended as a practical starting point for a proposal, thesis, or paper section. The list is selective rather than exhaustive.

## 1. Legal and Regulatory RAG

These papers are the closest match to the retrieval-augmented legal QA setting used in this project.

### LegalRAG: A Hybrid RAG System for Multilingual Legal Information Retrieval

- Focus: multilingual legal and regulatory QA
- Relevance: very close to this repository because it targets bilingual Bangla-English legal retrieval and QA
- Importance: probably the nearest published or preprint-style match to the overall direction of this project
- Domain: Bangladesh Police Gazettes
- Link: http://arxiv.org/abs/2504.16121v1

### Grounded Answers from Multi-Passage Regulations: Learning-to-Rank for Regulatory RAG

- Focus: multi-passage regulatory QA, learning-to-rank, citation-grounded generation
- Relevance: highly relevant for evidence packing, multi-passage retrieval, and faithful regulatory answer generation
- Importance: useful methodological reference for retrieval design and grounded answer evaluation
- Link: https://aclanthology.org/2025.nllp-1.10/

### RAGulator: Effective RAG for Regulatory Question Answering

- Focus: practical RAG pipeline for regulatory QA
- Relevance: useful baseline reference for regulatory retrieval and answer generation system design
- Importance: useful comparison point when describing end-to-end regulatory QA systems
- Link: https://aclanthology.org/2025.regnlp-1.18/

### RIRAG: A Bi-Directional Retrieval-Enhanced Framework for Financial Legal QA in ObliQA Shared Task

- Focus: financial and legal QA with retrieval-enhanced generation
- Relevance: especially useful if this repository grows toward tax-finance question answering benchmarks
- Importance: helpful for framing legal-financial QA as a realistic subdomain rather than a generic QA task
- Link: https://aclanthology.org/2025.regnlp-1.17/

### HyPA-RAG: A Hybrid Parameter Adaptive Retrieval-Augmented Generation System for AI Legal and Policy Applications

- Focus: adaptive hybrid RAG for legal and policy applications
- Relevance: relevant to hybrid retrieval, reranking, and system-level legal RAG design
- Importance: useful when positioning `bangla-tax-rag` among modern legal/policy RAG pipelines
- Link: https://aclanthology.org/2025.naacl-industry.79/

## 2. Legal QA and Retrieval Benchmarks

These works are useful for thinking about evaluation design, benchmark construction, and legal retrieval difficulty.

### ObliQA-MP Context

The NLLP 2025 paper above extends the ObliQA line into multi-passage regulatory QA. It is especially useful if you want to justify:

- multi-passage evidence aggregation
- citation-grounded answers
- retrieval-first evaluation

### KoBLEX: Open Legal Question Answering with Multi-hop Reasoning

- Focus: provision-grounded legal QA benchmark
- Relevance: useful for framing legal QA beyond single-fact retrieval
- Importance: highlights the need for benchmark design that respects legal structure and reasoning
- Link: https://aclanthology.org/2025.emnlp-main.200/

### GRAF: Graph Retrieval Augmented by Facts for Romanian Legal Multi-Choice Question Answering

- Focus: graph-enhanced retrieval for legal QA
- Relevance: useful if the project later incorporates graph or citation-network retrieval
- Importance: demonstrates that legal retrieval often benefits from structure-aware augmentation
- Link: https://aclanthology.org/2025.findings-acl.659/

### Applying Deep Neural Network to Retrieve Relevant Civil Law Articles

- Focus: retrieval of relevant law articles
- Relevance: older but directly relevant to the legal provision retrieval problem
- Importance: useful as an early legal retrieval baseline reference
- Link: https://aclanthology.org/R17-2007/

## 3. Bengali and Bangla QA Resources

These works are not always legal-domain-specific, but they are important for positioning the Bengali-language side of the project.

### BEnQA: A Question Answering Benchmark for Bengali and English

- Focus: benchmark QA for Bengali and English
- Relevance: useful for general bilingual QA evaluation design
- Importance: supports the claim that Bengali QA benchmarking exists but legal/tax QA remains underexplored
- Link: https://aclanthology.org/2024.findings-acl.68/

### BanglaRQA: A Benchmark Dataset for Under-resourced Bangla Language Reading Comprehension-based Question Answering with Diverse Question-Answer Types

- Focus: Bangla reading-comprehension QA
- Relevance: useful for Bengali QA background and dataset discussion
- Importance: supports the low-resource motivation for Bangla QA work
- Link: https://aclanthology.org/2022.findings-emnlp.186/

### bnContextQA

- Focus: long-context question answering in Bangla
- Relevance: useful if this repository evolves toward longer-context generation or direct long-context answering
- Importance: helps position this project relative to long-context Bangla QA
- Link: https://aclanthology.org/2025.banglalp-1.29/

## 4. Bangla OCR and Document Processing

Because this project works with difficult Bangla PDFs, OCR and document processing are part of the research story, not just engineering details.

### Gold Standard Bangla OCR Dataset: An In-Depth Look at Data Preprocessing and Annotation Processes

- Focus: Bangla OCR data and annotation quality
- Relevance: very useful when motivating OCR-first ingestion for Bangla legal documents
- Importance: supports the claim that OCR quality is a first-order research variable for Bangla document QA
- Link: https://aclanthology.org/2023.emnlp-industry.44/

### Nayana OCR

- Focus: OCR for low-resource languages including Bengali
- Relevance: useful for framing OCR challenges in multilingual or low-resource document settings
- Importance: useful when discussing why Bangla PDF ingestion is hard
- Link: https://aclanthology.org/2025.lm4uc-1.11/

## 5. What Makes This Repository Different

Based on the works above, `bangla-tax-rag` still has room for a meaningful contribution.

### Closest Existing Work

The closest work is `LegalRAG`, because it is:

- bilingual
- legal/regulatory
- Bangladesh-focused
- retrieval-augmented

However, this repository differs in a few important ways:

- it focuses on tax and legal PDF ingestion, not only downstream QA
- it explicitly includes OCR-aware ingestion and chunk quality as research variables
- it emphasizes chunk inspection, evidence selection, abstention, and citation verification
- it is designed for local reproducible experimentation through FastAPI and Streamlit
- it can support both Bangla tax circulars and English tax statutes in one pipeline

### Likely Novel Contribution Space

The strongest novelty space for this project is probably not “yet another legal RAG pipeline.” It is more likely:

1. Bangla tax/legal document ingestion with OCR-aware chunking
2. Evidence-grounded QA with section-, tax-year-, and authority-aware retrieval
3. A benchmark and evaluation setup for Bangla or Bangladesh-specific tax/legal QA
4. A study of how chunking quality and OCR quality affect downstream retrieval and grounded generation

## 6. How To Position A Paper

If you write a paper from this repository, a strong related-work positioning could be:

- Legal and regulatory RAG systems exist, including multilingual and citation-grounded approaches.
- Bengali QA benchmarks exist, but they are not focused on tax/legal documents.
- Bangla OCR research exists, but OCR quality is rarely evaluated jointly with legal QA pipelines.
- There is still limited work on Bangladesh-specific tax/legal QA with OCR-aware ingestion, structured chunking, evidence-grounded retrieval, and abstention-aware answer generation.

## 7. Suggested Gap Statement

You can adapt a gap statement like this:

> Prior work has studied legal and regulatory RAG, multilingual legal retrieval, Bengali question answering, and Bangla OCR independently. However, there is still limited work on an OCR-aware, retrieval-first, evidence-grounded QA pipeline for Bangladesh-specific tax and legal PDFs that jointly evaluates chunk quality, hybrid retrieval, citation-grounded generation, and abstention behavior.

## 8. Suggested Citation Groups For Your Paper

If you write a related-work section, one clean structure is:

1. Legal and regulatory RAG
2. Legal QA and provision retrieval
3. Bengali and Bangla QA
4. Bangla OCR and document understanding
5. Gap and contribution of the present work

## 9. Practical Advice

For a paper based on this repository:

- cite `LegalRAG` as the nearest Bangladesh/Bangla legal RAG work
- cite the NLLP and RegNLP papers for regulatory RAG design
- cite Bengali QA benchmarks to show the language-resource context
- cite Bangla OCR work to justify OCR-first ingestion experiments
- make your real contribution about evaluation and system design choices, not just tool integration

## Sources

- LegalRAG: A Hybrid RAG System for Multilingual Legal Information Retrieval  
  http://arxiv.org/abs/2504.16121v1
- Grounded Answers from Multi-Passage Regulations: Learning-to-Rank for Regulatory RAG  
  https://aclanthology.org/2025.nllp-1.10/
- RAGulator: Effective RAG for Regulatory Question Answering  
  https://aclanthology.org/2025.regnlp-1.18/
- RIRAG: A Bi-Directional Retrieval-Enhanced Framework for Financial Legal QA in ObliQA Shared Task  
  https://aclanthology.org/2025.regnlp-1.17/
- HyPA-RAG: A Hybrid Parameter Adaptive Retrieval-Augmented Generation System for AI Legal and Policy Applications  
  https://aclanthology.org/2025.naacl-industry.79/
- BEnQA: A Question Answering Benchmark for Bengali and English  
  https://aclanthology.org/2024.findings-acl.68/
- BanglaRQA: A Benchmark Dataset for Under-resourced Bangla Language Reading Comprehension-based Question Answering with Diverse Question-Answer Types  
  https://aclanthology.org/2022.findings-emnlp.186/
- Gold Standard Bangla OCR Dataset: An In-Depth Look at Data Preprocessing and Annotation Processes  
  https://aclanthology.org/2023.emnlp-industry.44/
- bnContextQA  
  https://aclanthology.org/2025.banglalp-1.29/
- Nayana OCR  
  https://aclanthology.org/2025.lm4uc-1.11/
