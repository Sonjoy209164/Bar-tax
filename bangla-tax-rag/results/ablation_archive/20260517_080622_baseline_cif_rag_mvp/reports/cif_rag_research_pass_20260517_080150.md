# CIF-RAG Research Evaluation Pass

- Run ID: `20260517_080150`
- Created: `2026-05-17T08:01:50.582761+00:00`
- Dataset: `/home/sonjoy/Bar tax/bangla-tax-rag/evaluation/cif_counterfactual_commerce_set.jsonl`
- Catalog: `/home/sonjoy/Bar tax/bangla-tax-rag/data/inventory/catalog.jsonl`

## Metrics

| Metric | Value |
|---|---:|
| Cases | 7 |
| Overall pass rate | 100.0% |
| Planner pass rate | 100.0% |
| Claim contract pass rate | 100.0% |
| Risk policy pass rate | 100.0% |
| Avg latency | 0.36 ms |

## Case Results

| Case | Decision | Query Family | Safe | Issues |
|---|---|---|---:|---|
| `cif_exact_product_photo` | `confirmed_exact` | `exact_product_check` | True |  |
| `cif_same_design_white` | `confirmed_same_design_variant` | `same_design_color_intervention` | True |  |
| `cif_color_missing_blue` | `similar_style` | `color_availability` | True |  |
| `cif_size_available_m` | `confirmed_exact` | `size_availability` | True |  |
| `cif_size_unavailable_m` | `confirmed_exact` | `size_availability` | True |  |
| `cif_reference_exact_demoted` | `similar_style` | `exact_product_check` | True |  |
| `cif_similar_bag_reference` | `similar_style` | `similar_style_search` | True |  |

## Interpretation

This eval checks the architectural pieces of CIF-RAG: counterfactual planning, typed commerce claims, and risk-cost policy. It is complementary to visual retrieval evaluation.