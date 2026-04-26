# PlanRAG-Commerce: Research Proposal

## Working Title

**PlanRAG-Commerce: Verifiable Answer Planning for Grounded Conversational Product Recommendation**

## One-Line Summary

This project studies whether an ecommerce chatbot becomes more accurate, logical, and trustworthy when it separates retrieved products from recommended products using explicit answer planning and verification before natural-language generation.

## Research Motivation

Modern ecommerce chatbots often fail in a predictable way: they retrieve semantically similar products and then present them as if they are valid recommendations. For example, a dense retriever may surface a wireless keyboard for a query about wireless headphones because both share broad terms such as "wireless" and "premium." A normal RAG chatbot can then turn that weak retrieval into a confident but illogical sales answer.

This project reframes the problem from "make the chatbot sound better" to a research-grade AI systems problem:

```text
How can a conversational commerce assistant produce natural sales/support answers while remaining faithful to structured product truth, exact availability, category constraints, and recommendation logic?
```

The core hypothesis is that a separate **answer planning layer** can improve ecommerce RAG quality by distinguishing:

- products that were merely retrieved
- products that are safe to recommend
- products that are acceptable fallbacks
- products that are valid cross-sells
- products that should be excluded from the answer

## Current System Context

The current system is a three-layer architecture:

```text
Next.js frontend -> Express backend -> PostgreSQL source of truth
                                      -> Python RAG sidecar for AI features
```

The Python RAG sidecar currently supports:

- mirrored product catalog ingestion through `/inventory/items/upsert`
- delete sync through `/inventory/items/delete`
- semantic search through `/inventory/search`
- natural support/sales chat through `/inventory/ask`
- routing between normal and agentic paths through `/inventory/route`
- bounded inventory-agentic retrieval through `/inventory/agentic/ask`
- answer planning and verification metadata in chat responses

PostgreSQL remains the source of truth. The RAG service is an AI mirror, not the operational inventory database.

## Research Problem

Most RAG systems treat retrieved evidence as if it is directly usable in generated answers. In ecommerce, that assumption is dangerous. Retrieval candidates may be semantically related but commercially inappropriate.

Example:

```text
Query: "Recommend the best premium wireless headphones for a customer"
Retrieved candidates:
- Auralite Flex ANC Headphones
- EchoWave Studio Earbuds
- KeyForge Mechanical Keyboard
- GlidePoint Wireless Mouse

Bad behavior:
- Recommend keyboard as fallback because it is wireless and cheaper.

Better behavior:
- Recommend Auralite headphones.
- Use EchoWave earbuds as fallback.
- Exclude keyboard and mouse from recommendation logic.
```

This project studies whether explicit answer planning can reduce those failures.

## Core Research Questions

### RQ1: Does answer planning improve recommendation coherence?

Does separating retrieval candidates into primary, alternative, cross-sell, and excluded products reduce wrong-category recommendations compared with normal RAG?

Expected finding:

```text
Hybrid RAG + answer planning should reduce wrong-category fallback recommendations.
```

### RQ2: Does verification reduce hallucinated or unsupported sales claims?

Can a lightweight verifier catch illogical recommendation plans before the model writes the final answer?

Expected finding:

```text
Plan verification should reduce unsupported product claims, wrong fallbacks, and invalid cross-sells.
```

### RQ3: Does structured metadata improve product explanations?

Does using structured fields such as attributes and metadata improve answer usefulness and factuality compared with title/description-only RAG?

Expected finding:

```text
Metadata-aware planning should improve feature correctness and explanation quality.
```

### RQ4: Can exact no-match abstention prevent irrelevant product suggestions?

Can ecommerce RAG distinguish "no exact product exists" from "some semantically nearby product exists"?

Expected finding:

```text
Lexical anchoring + abstention should reduce false-positive suggestions for missing products.
```

### RQ5: When is agentic RAG worth the latency?

Can a router preserve quality while reducing latency by sending only complex internal questions to agentic retrieval?

Expected finding:

```text
Normal planned RAG should be better for customer-facing chat, while agentic RAG should be reserved for multi-step internal analysis.
```

## Proposed Method

The proposed system is:

```text
User question
  -> intent classification
  -> hybrid retrieval
  -> ecommerce reranking
  -> answer planning
  -> plan verification
  -> grounded natural generation
  -> final answer + product cards + plan metadata
```

## Answer Plan Schema

The system produces an explicit answer plan:

```json
{
  "intent": "sales_premium",
  "primary_product_id": "seed-audio-001",
  "alternative_product_ids": ["seed-audio-002"],
  "cross_sell_product_ids": [],
  "excluded_product_ids": ["seed-compute-002", "seed-compute-003"],
  "reasoning_steps": [
    "Selected Auralite Flex ANC Headphones because it is the strongest premium match after stock, relevance, and quality ranking.",
    "Kept recommendation logic anchored to the Audio category unless an explicit cross-sell is requested.",
    "Excluded unrelated retrieval hits from recommendation logic: KeyForge Mechanical Keyboard and GlidePoint Wireless Mouse."
  ],
  "metadata_used": [
    "attributes.battery_hours",
    "attributes.connectivity",
    "metadata.source_of_truth"
  ],
  "abstain": false,
  "abstention_reason": null
}
```

The final answer generator is instructed to follow this plan rather than freely choosing products.

## Verification Schema

The verifier returns:

```json
{
  "passed": true,
  "issues": []
}
```

Potential verification issues:

- primary product missing from evidence
- alternative product not related to primary product
- cross-sell not present in evidence
- same product both used and excluded
- answer plan recommends a product from an unrelated category
- answer plan uses metadata not present in the product record

## Baselines

Evaluate the proposed method against:

1. **Dense-only RAG**

Dense retrieval followed by direct LLM generation.

2. **Hybrid retrieval RAG**

Sparse/dense retrieval followed by direct LLM generation.

3. **Hybrid retrieval + deterministic templates**

Retrieval plus handcrafted answer templates.

4. **Hybrid retrieval + natural generation**

Retrieval plus LLM rewrite, but no explicit plan.

5. **Hybrid retrieval + answer planning**

Retrieval, reranking, answer plan, and LLM generation.

6. **Hybrid retrieval + answer planning + verifier**

Full proposed system.

7. **Always-agentic RAG**

Agentic retrieval for every query.

8. **Router-based RAG**

Normal planned RAG for simple questions and agentic path for complex questions.

## Ablation Studies

Run controlled ablations:

- remove lexical anchoring
- remove category constraints
- remove metadata from evidence
- remove answer plan
- remove verifier
- remove natural generation
- remove exact no-match abstention
- use dense-only retrieval
- use normal RAG for all questions
- use agentic RAG for all questions

## Evaluation Dataset

Create a benchmark named:

```text
CommercePlanQA
```

Recommended size:

```text
300-1000 questions
```

Question categories:

- exact lookup
- no-match lookup
- product detail
- semantic product search
- recommendation
- budget recommendation
- premium recommendation
- comparison
- price objection
- availability objection
- quality objection
- cross-sell / bundle
- restock support
- adversarial prompt
- internal manager analysis

Example rows:

```json
{
  "question_id": "q-001",
  "question": "Recommend the best premium wireless headphones for a customer",
  "intent": "sales_premium",
  "expected_primary_product_ids": ["seed-audio-001"],
  "acceptable_alternative_product_ids": ["seed-audio-002"],
  "forbidden_product_ids": ["seed-compute-002", "seed-compute-003"],
  "must_abstain": false,
  "required_metadata_fields": ["attributes.connectivity", "attributes.battery_hours"],
  "notes": "Keyboard and mouse are semantically related through wireless, but should not be recommended as fallback headphones."
}
```

```json
{
  "question_id": "q-002",
  "question": "Do you have any bike?",
  "intent": "exact_lookup",
  "expected_primary_product_ids": [],
  "acceptable_alternative_product_ids": [],
  "forbidden_product_ids": ["seed-watch-001"],
  "must_abstain": true,
  "required_metadata_fields": [],
  "notes": "The system must not suggest watches or other semantically nearby products."
}
```

## Automatic Metrics

### Retrieval Metrics

- top-1 product accuracy
- top-3 product recall
- mean reciprocal rank
- wrong-category rate
- no-match false-positive rate

### Recommendation Metrics

- primary recommendation accuracy
- alternative recommendation accuracy
- cross-sell precision
- forbidden product violation rate
- same-category fallback rate
- in-stock recommendation rate

### Factuality Metrics

- price correctness
- stock correctness
- category correctness
- brand correctness
- attribute correctness
- hallucinated feature rate

### Abstention Metrics

- abstention precision
- abstention recall
- abstention F1
- false abstention rate
- false recommendation rate

### Planning Metrics

- plan validity rate
- verifier pass rate
- verifier issue rate
- excluded-product correctness
- metadata usage correctness

### Generation Metrics

- groundedness
- helpfulness
- naturalness
- clarity
- sales usefulness
- support usefulness

### Operational Metrics

- latency p50/p95
- token count
- model timeout rate
- fallback rate from natural to deterministic
- agentic escalation rate

## Human Evaluation

Use a 1-5 scale for:

- answer helpfulness
- recommendation logic
- sales usefulness
- trustworthiness
- naturalness
- concise communication
- whether the bot should have abstained

Annotators should also mark:

- unsupported product claim
- wrong product type
- wrong category fallback
- hallucinated feature
- overconfident no-evidence answer
- irrelevant cross-sell

## Expected Contributions

1. A verifiable answer-planning framework for ecommerce RAG.

2. A benchmark for grounded conversational product recommendation.

3. Evidence that retrieval candidates should be separated from recommended candidates.

4. A practical verifier for product recommendation coherence.

5. An evaluation of metadata-aware answer generation.

6. A routing strategy for normal RAG versus agentic RAG in ecommerce chat.

## Key System Features To Implement

### 1. Evaluation Harness

Create:

```text
evaluation/commerce_questions.jsonl
evaluation/run_inventory_eval.py
evaluation/metrics.py
evaluation/reports/
```

### 2. Experiment Runner

Each run should log:

```json
{
  "question_id": "q-001",
  "question": "Recommend premium headphones",
  "retrieved_product_ids": [],
  "recommended_product_ids": [],
  "cross_sell_product_ids": [],
  "excluded_product_ids": [],
  "answer_plan": {},
  "verification": {},
  "answer": "...",
  "latency_ms": 1234,
  "answer_engine": "natural"
}
```

### 3. Reranking Improvements

Add explicit ecommerce scoring:

```text
final_score =
  semantic_score
  + lexical_score
  + category_match
  + brand_match
  + product_type_match
  + stock_score
  + price_fit
  + metadata_match
  - unrelated_category_penalty
```

### 4. Verifier Improvements

Add checks for:

- final answer mentions only evidence-backed products
- answer does not mention excluded products as recommendations
- alternatives are related to primary product
- cross-sells require explicit cross-sell intent
- metadata claims are backed by product attributes

### 5. Agentic Evaluation

Use agentic mode only for questions requiring:

- multi-step reasoning
- restock prioritization
- cross-category analysis
- missing data explanation
- manager/operator workflows

## Related Work Reading List

Essential papers:

- Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", NeurIPS 2020.
- Karpukhin et al., "Dense Passage Retrieval for Open-Domain Question Answering", EMNLP 2020.
- Guu et al., "REALM: Retrieval-Augmented Language Model Pre-Training", ICML 2020.
- Khattab and Zaharia, "ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT", SIGIR 2020.
- Formal et al., "SPLADE: Sparse Lexical and Expansion Model for First Stage Ranking", SIGIR 2021.
- Gao et al., "Precise Zero-Shot Dense Retrieval without Relevance Labels", ACL 2023.
- Asai et al., "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection", ICLR 2024.
- Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models", ICLR 2023.
- Li et al., "Towards Deep Conversational Recommendations", NeurIPS 2018.
- Chen et al., "Towards Knowledge-Based Recommender Dialog System", EMNLP-IJCNLP 2019.
- Wang et al., "Towards Unified Conversational Recommender Systems via Knowledge-Enhanced Prompt Learning", KDD 2022.
- Gao et al., "Enabling Large Language Models to Generate Text with Citations", EMNLP 2023.

## 30-Day Research Plan

### Week 1: Benchmark Design

- Define question categories.
- Create 100 initial benchmark questions.
- Label expected primary, alternative, forbidden, and abstention fields.
- Add evaluation JSONL format.
- Implement basic metric functions.

### Week 2: Experiment Harness

- Build `run_inventory_eval.py`.
- Run baselines:
  - dense-only
  - hybrid retrieval
  - hybrid + natural generation
  - hybrid + answer planning
- Save structured outputs.
- Create first metrics report.

### Week 3: Planning And Verification Improvements

- Add stronger ecommerce reranking.
- Add product-type matching.
- Add answer-level verifier.
- Add metadata claim checking.
- Run ablations.

### Week 4: Analysis And Write-Up

- Run final experiments on 300-1000 questions.
- Build tables and plots.
- Write research report:
  - motivation
  - system design
  - experiments
  - results
  - limitations
  - future work

## Expected Results Table

| System | Wrong-Category Rate | No-Match False Positive | Recommendation Accuracy | Hallucinated Feature Rate | Latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dense RAG | high | high | medium | medium | low |
| Hybrid RAG | medium | medium | medium | medium | low |
| Hybrid + Natural Generation | medium | medium | medium | high risk | medium |
| Hybrid + Answer Plan | low | low | high | low | medium |
| Hybrid + Plan + Verifier | lowest | lowest | highest | lowest | medium |
| Always Agentic | low | low | high | low | high |
| Router-Based | low | low | high | low | balanced |

## Risks And Limitations

- The current inventory agentic path is catalog-bound and does not yet access live sales, orders, suppliers, or margins.
- The benchmark may overfit to synthetic seed products unless real catalog data is included.
- Human evaluation is needed because naturalness and sales usefulness are hard to measure automatically.
- Metadata quality strongly affects explanation quality.
- A small local model may produce weaker natural language than a stronger hosted model, but the planning layer should still improve logic.

## Future Extensions

- Add sales history and order analytics as tool-connected data domains.
- Add supplier lead-time reasoning for restock decisions.
- Add customer preference memory.
- Add personalized recommendation logic.
- Add streaming responses for better chat UX.
- Add multilingual evaluation for Bangla and English ecommerce queries.
- Add product review and return-rate data.

## Research Claim

The central claim is:

```text
In ecommerce RAG, retrieved products should not be treated as recommended products. A separate answer-planning and verification layer improves recommendation coherence, abstention behavior, and factual product explanations while preserving natural conversation quality.
```

This claim is measurable, useful, and defensible.

