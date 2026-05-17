# Ablation Archive

- Archive ID: `20260517_080736_baseline_cif_rag_mvp_final`
- Label: `baseline_cif_rag_mvp_final`
- Created: `2026-05-17T08:07:36.921676+00:00`
- Branch: `inventory_research`
- HEAD: `6ac33267c9e9fb269675183839558a26e9e96c28`

## Reports

- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/reports/cif_rag_research_pass_20260517_080150.json` (87883 bytes)
- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/reports/cif_rag_research_pass_20260517_080150.md` (1393 bytes)
- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/reports/q1_image_research_pass_20260517_064010.json` (740904 bytes)
- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/reports/q1_image_research_pass_20260517_064010.md` (24235 bytes)
- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/reports/q1_image_research_pass_20260517_064028.json` (330775 bytes)
- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/reports/q1_image_research_pass_20260517_064028.md` (7817 bytes)
- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/reports/q1_image_research_pass_20260517_064205.json` (703566 bytes)
- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/reports/q1_image_research_pass_20260517_064205.md` (15263 bytes)

## Datasets

- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/datasets/q1_image_search_research_set.jsonl` (12461 bytes)
- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/datasets/cif_counterfactual_commerce_set.jsonl` (3663 bytes)

## Docs

- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/docs/q1_image_search_research_pipeline.md` (5441 bytes)
- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/docs/cif_rag_architecture_plan.md` (19236 bytes)
- `results/ablation_archive/20260517_080736_baseline_cif_rag_mvp_final/docs/learn_image.md` (27667 bytes)

## Metrics Snapshot

### `results/cif_rag_research_pass_20260517_080150.json`

```json
{
  "cases": 7,
  "pass_rate": 1.0,
  "planner_pass_rate": 1.0,
  "claim_contract_pass_rate": 1.0,
  "risk_policy_pass_rate": 1.0,
  "avg_latency_ms": 0.36428571428571427
}
```

### `results/q1_image_research_pass_20260517_064010.json`

```json
{
  "by_method": {
    "full_system": {
      "cases": 20,
      "strict_pass_rate": 0.4,
      "label_accuracy": 0.0,
      "primary_or_top3_accuracy": 0.0,
      "target_top3_recall": 0.0,
      "same_design_variant_recall": 0.0,
      "available_color_recall": 0.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.5541482707485557
    },
    "metadata_baseline": {
      "cases": 20,
      "strict_pass_rate": 0.4,
      "label_accuracy": 0.0,
      "primary_or_top3_accuracy": 0.0,
      "target_top3_recall": 0.0,
      "same_design_variant_recall": 0.0,
      "available_color_recall": 0.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 1.0053353384137154
    },
    "naive_oracle_top1": {
      "cases": 20,
      "strict_pass_rate": 0.0,
      "label_accuracy": 0.7142857142857143,
      "primary_or_top3_accuracy": 0.9,
      "target_top3_recall": 0.8055555555555556,
      "same_design_variant_recall": 0.16666666666666666,
      "available_color_recall": 0.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.020711059914901853
    },
    "no_identity_ablation": {
      "cases": 20,
      "strict_pass_rate": 0.4,
      "label_accuracy": 0.14285714285714285,
      "primary_or_top3_accuracy": 0.0,
      "target_top3_recall": 0.0,
      "same_design_variant_recall": 0.0,
      "available_color_recall": 0.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 6.892296043224633
    },
    "policy_oracle": {
      "cases": 20,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 0.9722222222222222,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.3267808584496379
    }
  },
  "full_system_by_task": {
    "cross_category_guard": {
      "cases": 6,
      "strict_pass_rate": 0.6666666666666666,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 0.0,
      "target_top3_recall": 0.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.49718801164999604
    },
    "exact_product": {
      "cases": 1,
      "strict_pass_rate": 0.0,
      "label_accuracy": 0.0,
      "primary_or_top3_accuracy": 0.0,
      "target_top3_recall": 0.0,
      "same_design_variant_recall": 0.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.5288349930197
    },
    "missing_fact_safety": {
      "cases": 1,
      "strict_pass_rate": 0.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 0.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 1.1357790790498257
    },
    "reference_guard": {
      "cases": 1,
      "strict_pass_rate": 0.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 0.0,
      "target_top3_recall": 0.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.7398329908028245
    },
    "requested_color_missing": {
      "cases": 1,
      "strict_pass_rate": 0.0,
      "label_accuracy": 0.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 0.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.5851610330864787
    },
    "same_design_variant": {
      "cases": 1,
      "strict_pass_rate": 0.0,
      "label_accuracy": 0.0,
      "primary_or_top3_accuracy": 0.0,
      "target_top3_recall": 0.0,
      "same_design_variant_recall": 0.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.7145650452002883
    },
    "similar_category_search": {
      "cases": 5,
      "strict_pass_rate": 0.8,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.4250301979482174
    },
    "size_availability": {
      "cases": 3,
      "strict_pass_rate": 0.0,
      "label_accuracy": 0.0,
      "primary_or_top3_accuracy": 0.0,
      "target_top3_recall": 0.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.5671140582611164
    },
    "variant_listing": {
      "cases": 1,
      "strict_pass_rate": 0.0,
      "label_accuracy": 0.0,
      "primary_or_top3_accuracy": 0.0,
      "target_top3_recall": 0.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 0.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.5691710393875837
    }
  }
}
```

### `results/q1_image_research_pass_20260517_064028.json`

```json
{
  "by_method": {
    "full_system": {
      "cases": 20,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 0.9722222222222222,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.6652504380326718
    },
    "naive_oracle_top1": {
      "cases": 20,
      "strict_pass_rate": 0.0,
      "label_accuracy": 0.7142857142857143,
      "primary_or_top3_accuracy": 0.9,
      "target_top3_recall": 0.8055555555555556,
      "same_design_variant_recall": 0.16666666666666666,
      "available_color_recall": 0.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.023068295558914542
    },
    "policy_oracle": {
      "cases": 20,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 0.9722222222222222,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.35697456332854927
    }
  },
  "full_system_by_task": {
    "cross_category_guard": {
      "cases": 6,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.4701851673113803
    },
    "exact_product": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.7605419959872961
    },
    "missing_fact_safety": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 1.1933069908991456
    },
    "reference_guard": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 1.4965770533308387
    },
    "requested_color_missing": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.8915079524740577
    },
    "same_design_variant": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.7713320665061474
    },
    "similar_category_search": {
      "cases": 5,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.4272043704986572
    },
    "size_availability": {
      "cases": 3,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.7720269495621324
    },
    "variant_listing": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 0.75,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.9185289964079857
    }
  }
}
```

### `results/q1_image_research_pass_20260517_064205.json`

```json
{
  "by_method": {
    "full_system": {
      "cases": 20,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 0.9722222222222222,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.6247980578336865
    },
    "metadata_baseline": {
      "cases": 20,
      "strict_pass_rate": 0.4,
      "label_accuracy": 0.0,
      "primary_or_top3_accuracy": 0.0,
      "target_top3_recall": 0.0,
      "same_design_variant_recall": 0.0,
      "available_color_recall": 0.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 1.1099132592789829
    },
    "naive_oracle_top1": {
      "cases": 20,
      "strict_pass_rate": 0.0,
      "label_accuracy": 0.7142857142857143,
      "primary_or_top3_accuracy": 0.9,
      "target_top3_recall": 0.8055555555555556,
      "same_design_variant_recall": 0.16666666666666666,
      "available_color_recall": 0.0,
      "forbidden_violation_rate": 1.0,
      "false_exact_on_reference_rate": 1.0,
      "avg_latency_ms": 0.02104609156958759
    },
    "no_identity_ablation": {
      "cases": 20,
      "strict_pass_rate": 0.65,
      "label_accuracy": 0.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 0.9722222222222222,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 0.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 5.989622103516012
    },
    "policy_oracle": {
      "cases": 20,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 0.9722222222222222,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.32701175659894943
    }
  },
  "full_system_by_task": {
    "cross_category_guard": {
      "cases": 6,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.4863691477415462
    },
    "exact_product": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.7627259474247694
    },
    "missing_fact_safety": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 1.2078949948772788
    },
    "reference_guard": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.8456320501863956
    },
    "requested_color_missing": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.8921100525185466
    },
    "same_design_variant": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.7637980161234736
    },
    "similar_category_search": {
      "cases": 5,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.40002542082220316
    },
    "size_availability": {
      "cases": 3,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 1.0,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.7631036763389906
    },
    "variant_listing": {
      "cases": 1,
      "strict_pass_rate": 1.0,
      "label_accuracy": 1.0,
      "primary_or_top3_accuracy": 1.0,
      "target_top3_recall": 0.75,
      "same_design_variant_recall": 1.0,
      "available_color_recall": 1.0,
      "forbidden_violation_rate": 0.0,
      "false_exact_on_reference_rate": 0.0,
      "avg_latency_ms": 0.8161470759660006
    }
  }
}
```

## Reproduction Commands

```bash
.venv/bin/python scripts/run_q1_image_research_pass.py --engine auto --methods full_system metadata_baseline no_identity_ablation policy_oracle naive_oracle_top1
.venv/bin/python scripts/run_cif_rag_research_eval.py
.venv/bin/python scripts/archive_ablation_results.py --label baseline_cif_rag_mvp_final
```
