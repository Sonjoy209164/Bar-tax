from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_lereve_image_search_comparison import (  # noqa: E402
    build_catalog_factor_cache,
    compute_metrics,
    compute_per_category_metrics,
    decide_vectorized_cif_top,
    load_catalog,
    metadata_factor_score_arrays,
    rank_pair_score,
    rank_single_score,
    read_jsonl,
    row_from_vectorized_hits,
    top_indices,
    top_indices_pair,
)
from scripts.run_lereve_clip100_baseline import ratio, relative_or_abs  # noqa: E402


DEFAULT_CATALOG = ROOT / "data" / "inventory" / "lereve_clip20000_catalog.jsonl"
DEFAULT_EVAL = ROOT / "evaluation" / "lereve_clip20000_exact_eval.jsonl"
DEFAULT_OUT_DIR = Path("/mnt/nvme0n1p3/sonjoy/lereve_model_ablations/results")
DEFAULT_CACHE_DIR = Path("/mnt/nvme0n1p3/sonjoy/lereve_model_ablations/vector_cache")
DEFAULT_HF_HOME = Path("/mnt/nvme0n1p3/sonjoy/hf_cache")


@dataclass(frozen=True)
class ModelSpec:
    key: str
    model_id: str
    kind: str
    note: str


MODEL_SPECS = {
    "clip": ModelSpec(
        key="clip",
        model_id="openai/clip-vit-base-patch32",
        kind="clip",
        note="Generic CLIP baseline.",
    ),
    "fashion_clip": ModelSpec(
        key="fashion_clip",
        model_id="patrickjohncyh/fashion-clip",
        kind="clip",
        note="Fashion-domain CLIP-style model.",
    ),
    "dinov2": ModelSpec(
        key="dinov2",
        model_id="facebook/dinov2-small",
        kind="auto",
        note="Self-supervised visual representation baseline.",
    ),
    "siglip": ModelSpec(
        key="siglip",
        model_id="google/siglip-base-patch16-224",
        kind="auto",
        note="Modern CLIP-family image encoder baseline.",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run compact Le Reve visual backbone ablations: CLIP, FashionCLIP, DINOv2, SigLIP."
    )
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--eval", default=str(DEFAULT_EVAL))
    parser.add_argument("--models", nargs="+", default=["clip", "fashion_clip", "dinov2", "siglip"])
    parser.add_argument("--limit", type=int, default=0, help="Optional eval/catalog cap for smoke tests. 0 = all.")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--hf-home", default=str(DEFAULT_HF_HOME))
    args = parser.parse_args()

    configure_hf_cache(Path(args.hf_home))
    catalog = load_catalog(Path(args.catalog))
    cases = read_jsonl(Path(args.eval))
    if args.limit and args.limit > 0:
        selected_ids = {case["expected_primary_product_id"] for case in cases[: args.limit]}
        catalog = {pid: item for pid, item in catalog.items() if pid in selected_ids}
        cases = cases[: args.limit]
    if not catalog:
        raise SystemExit("No catalog rows to evaluate.")
    if not cases:
        raise SystemExit("No eval rows to evaluate.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    payload: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "catalog": relative_or_abs(Path(args.catalog)),
        "eval": relative_or_abs(Path(args.eval)),
        "products": len(catalog),
        "cases": len(cases),
        "models": {},
    }

    for model_key in args.models:
        spec = MODEL_SPECS.get(model_key)
        if spec is None:
            raise SystemExit(f"Unknown model key {model_key!r}. Available: {sorted(MODEL_SPECS)}")
        started = perf_counter()
        try:
            result = run_model(
                spec=spec,
                catalog=catalog,
                cases=cases,
                cache_dir=cache_dir,
                batch_size=args.batch_size,
                device_name=args.device,
            )
            result["latency_ms"] = round((perf_counter() - started) * 1000, 2)
        except Exception as exc:
            result = {
                "model_id": spec.model_id,
                "note": spec.note,
                "error": f"{type(exc).__name__}: {exc}",
                "latency_ms": round((perf_counter() - started) * 1000, 2),
            }
        payload["models"][model_key] = result
        json_path = out_dir / f"lereve_visual_backbone_ablation_{len(cases)}_{run_id}.json"
        md_path = out_dir / f"lereve_visual_backbone_ablation_{len(cases)}_{run_id}.md"
        write_json(json_path, compact_payload(payload))
        md_path.write_text(render_markdown(payload), encoding="utf-8")
        print_model_summary(model_key, result)

    print("Le Reve visual backbone ablation complete")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    return 0


def configure_hf_cache(hf_home: Path) -> None:
    hf_home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HF_HUB_CACHE", str(hf_home / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_home / "hub"))
    os.environ.setdefault("TORCH_HOME", str(hf_home / "torch"))


def run_model(
    *,
    spec: ModelSpec,
    catalog: dict[str, Any],
    cases: list[dict[str, Any]],
    cache_dir: Path,
    batch_size: int,
    device_name: str,
) -> dict[str, Any]:
    encoder = ImageBackboneEncoder(spec=spec, device_name=device_name)
    product_ids = list(catalog)
    catalog_paths = [catalog[pid].images[0].local_path for pid in product_ids]
    query_paths = [case["image_path"] for case in cases]
    all_paths = [str(path) for path in catalog_paths + query_paths]
    cache_path = cache_dir / f"{spec.key}_{safe_model_id(spec.model_id)}_{len(all_paths)}.npz"
    vectors = load_or_encode_vectors(
        encoder=encoder,
        image_paths=all_paths,
        cache_path=cache_path,
        batch_size=batch_size,
    )

    catalog_vectors = vectors[: len(product_ids)]
    query_vectors = vectors[len(product_ids):]
    product_index = {product_id: idx for idx, product_id in enumerate(product_ids)}
    catalog_matrix = normalize_matrix(catalog_vectors)
    query_matrix = normalize_matrix(query_vectors)
    catalog_factors = build_catalog_factor_cache(product_ids, catalog)
    empty_mask = np.zeros(len(product_ids), dtype=bool)

    visual_rows: list[dict[str, Any]] = []
    metadata_rows: list[dict[str, Any]] = []
    no_contract_rows: list[dict[str, Any]] = []
    no_risk_rows: list[dict[str, Any]] = []
    cif_rows: list[dict[str, Any]] = []

    for case_idx, case in enumerate(cases):
        expected_index = product_index.get(case["expected_primary_product_id"])
        visual_scores = catalog_matrix @ query_matrix[case_idx]
        metadata_scores, category_matches, color_matches = metadata_factor_score_arrays(
            case,
            catalog_factors,
            empty_mask,
        )
        final_scores = visual_scores + metadata_scores
        visual_top = top_indices(visual_scores, 10)
        metadata_top = top_indices_pair(final_scores, visual_scores, 10)
        no_contract_top, no_contract_decision = decide_vectorized_cif_top(
            metadata_top,
            clip_scores=visual_scores,
            final_scores=final_scores,
            metadata_scores=metadata_scores,
            category_matches=category_matches,
            color_matches=color_matches,
            catalog_factors=catalog_factors,
            use_claim_contracts=False,
            use_risk_policy=True,
        )
        no_risk_top, no_risk_decision = decide_vectorized_cif_top(
            metadata_top,
            clip_scores=visual_scores,
            final_scores=final_scores,
            metadata_scores=metadata_scores,
            category_matches=category_matches,
            color_matches=color_matches,
            catalog_factors=catalog_factors,
            use_claim_contracts=True,
            use_risk_policy=False,
        )
        cif_top, cif_decision = decide_vectorized_cif_top(
            metadata_top,
            clip_scores=visual_scores,
            final_scores=final_scores,
            metadata_scores=metadata_scores,
            category_matches=category_matches,
            color_matches=color_matches,
            catalog_factors=catalog_factors,
            use_claim_contracts=True,
            use_risk_policy=True,
        )

        visual_rows.append(
            row_from_vectorized_hits(
                case=case,
                expected_index=expected_index,
                rank=rank_single_score(visual_scores, expected_index),
                top_indices=visual_top,
                product_ids=product_ids,
                catalog=catalog,
                clip_scores=visual_scores,
                metadata_scores=np.zeros_like(metadata_scores),
                final_scores=visual_scores,
                category_matches=category_matches,
                color_matches=color_matches,
                decision=None,
            )
        )
        metadata_rows.append(
            row_from_vectorized_hits(
                case=case,
                expected_index=expected_index,
                rank=rank_pair_score(final_scores, visual_scores, expected_index),
                top_indices=metadata_top,
                product_ids=product_ids,
                catalog=catalog,
                clip_scores=visual_scores,
                metadata_scores=metadata_scores,
                final_scores=final_scores,
                category_matches=category_matches,
                color_matches=color_matches,
                decision=None,
            )
        )
        no_contract_rows.append(
            row_from_vectorized_hits(
                case=case,
                expected_index=expected_index,
                rank=rank_pair_score(final_scores, visual_scores, expected_index),
                top_indices=no_contract_top,
                product_ids=product_ids,
                catalog=catalog,
                clip_scores=visual_scores,
                metadata_scores=metadata_scores,
                final_scores=final_scores,
                category_matches=category_matches,
                color_matches=color_matches,
                decision=no_contract_decision,
            )
        )
        no_risk_rows.append(
            row_from_vectorized_hits(
                case=case,
                expected_index=expected_index,
                rank=rank_pair_score(final_scores, visual_scores, expected_index),
                top_indices=no_risk_top,
                product_ids=product_ids,
                catalog=catalog,
                clip_scores=visual_scores,
                metadata_scores=metadata_scores,
                final_scores=final_scores,
                category_matches=category_matches,
                color_matches=color_matches,
                decision=no_risk_decision,
            )
        )
        cif_rows.append(
            row_from_vectorized_hits(
                case=case,
                expected_index=expected_index,
                rank=rank_pair_score(final_scores, visual_scores, expected_index),
                top_indices=cif_top,
                product_ids=product_ids,
                catalog=catalog,
                clip_scores=visual_scores,
                metadata_scores=metadata_scores,
                final_scores=final_scores,
                category_matches=category_matches,
                color_matches=color_matches,
                decision=cif_decision,
            )
        )

    return {
        "model_id": spec.model_id,
        "note": spec.note,
        "embedding_dim": int(catalog_vectors.shape[1]),
        "cache_path": str(cache_path),
        "methods": {
            "visual_only": summarize_rows(visual_rows, decision_mode=False),
            "visual_metadata": summarize_rows(metadata_rows, decision_mode=False),
            "cif_without_claim_contracts": summarize_rows(no_contract_rows, decision_mode=True),
            "cif_without_risk_policy": summarize_rows(no_risk_rows, decision_mode=True),
            "cif_guarded": summarize_rows(cif_rows, decision_mode=True),
        },
    }


def decide_cif(
    ranked_indices: np.ndarray,
    *,
    visual_scores: np.ndarray,
    final_scores: np.ndarray,
    metadata_scores: np.ndarray,
    category_matches: np.ndarray,
    color_matches: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any] | None]:
    if len(ranked_indices) == 0:
        return ranked_indices, None
    top_index = int(ranked_indices[0])
    runner_up_index = int(ranked_indices[1]) if len(ranked_indices) > 1 else None
    category_safe = bool(category_matches[top_index])
    final_margin = float(final_scores[top_index] - final_scores[runner_up_index]) if runner_up_index is not None else 1.0
    visual_margin = float(visual_scores[top_index] - visual_scores[runner_up_index]) if runner_up_index is not None else 1.0
    risk_policy_passed = bool(visual_scores[top_index] >= 0.84 and (final_margin >= 0.025 or visual_margin >= 0.045))
    accepted_exact = category_safe and risk_policy_passed
    if accepted_exact:
        label = "confirmed_exact"
        reason = "category/score/margin evidence passed"
    elif not category_safe:
        label = "no_confident_match"
        reason = "category guard blocked exact product claim"
    elif visual_scores[top_index] >= 0.78:
        label = "similar_style"
        reason = "visually plausible but exact margin or score is unsafe"
    else:
        label = "no_confident_match"
        reason = "visual score below commerce-safe threshold"
    return ranked_indices, {
        "top_index": top_index,
        "decision_label": label,
        "accepted_exact": accepted_exact,
        "decision_reason": reason,
        "metadata_score": float(metadata_scores[top_index]),
        "category_match": bool(category_matches[top_index]),
        "color_match": bool(color_matches[top_index]),
    }


def summarize_rows(rows: list[dict[str, Any]], *, decision_mode: bool) -> dict[str, Any]:
    metrics = compute_metrics(rows, decision_mode=decision_mode)
    per_category = compute_per_category_metrics(rows, decision_mode=decision_mode)
    worst = sorted(per_category.items(), key=lambda item: item[1]["top5_recall"])[:8]
    return {
        "metrics": metrics,
        "worst_categories_by_top5": {cat: met for cat, met in worst},
        "sample_failures": compact_failures(rows),
    }


def compact_failures(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    failures = [row for row in rows if row.get("rank") != 1]
    output = []
    for row in failures[:limit]:
        top = row["hits"][0] if row.get("hits") else {}
        case = row["case"]
        output.append(
            {
                "case_id": case.get("case_id"),
                "expected": case.get("expected_primary_product_id"),
                "top1": top.get("product_id"),
                "rank": row.get("rank"),
                "top1_name": top.get("name"),
                "expected_name": case.get("name"),
            }
        )
    return output


class ImageBackboneEncoder:
    def __init__(self, *, spec: ModelSpec, device_name: str) -> None:
        self.spec = spec
        self.device = self._resolve_device(device_name)
        self.processor, self.model = self._load_model(spec)
        self.model.to(self.device)
        self.model.eval()

    def _resolve_device(self, device_name: str) -> str:
        if device_name != "auto":
            return device_name
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    def _load_model(self, spec: ModelSpec):
        if spec.kind == "clip":
            from transformers import CLIPModel, CLIPProcessor

            processor = CLIPProcessor.from_pretrained(spec.model_id)
            model = CLIPModel.from_pretrained(spec.model_id)
            return processor, model
        from transformers import AutoImageProcessor, AutoModel, AutoProcessor

        try:
            processor = AutoProcessor.from_pretrained(spec.model_id)
        except Exception:
            processor = AutoImageProcessor.from_pretrained(spec.model_id)
        model = AutoModel.from_pretrained(spec.model_id)
        return processor, model

    def encode_paths(self, image_paths: list[str], *, batch_size: int) -> np.ndarray:
        from PIL import Image
        import torch

        vectors: list[np.ndarray] = []
        for start in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[start:start + batch_size]
            images = []
            for path in batch_paths:
                with Image.open(path) as img:
                    images.append(img.convert("RGB").copy())
            inputs = self.processor(images=images, return_tensors="pt")
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            with torch.no_grad():
                if hasattr(self.model, "get_image_features"):
                    feats = self.model.get_image_features(**inputs)
                    feats = unwrap_model_features(feats)
                else:
                    output = self.model(**inputs)
                    feats = unwrap_model_features(output)
            feats = feats.detach().float().cpu().numpy()
            vectors.append(feats)
        return np.vstack(vectors).astype(np.float32)


def unwrap_model_features(output: Any) -> Any:
    if hasattr(output, "detach"):
        return output
    for attr in ("image_embeds", "pooler_output"):
        value = getattr(output, attr, None)
        if value is not None:
            return value
    hidden = getattr(output, "last_hidden_state", None)
    if hidden is not None:
        return hidden[:, 0]
    if isinstance(output, (tuple, list)) and output:
        first = output[0]
        if hasattr(first, "detach"):
            return first
    raise TypeError(f"Cannot unwrap image features from {type(output).__name__}")


def load_or_encode_vectors(
    *,
    encoder: ImageBackboneEncoder,
    image_paths: list[str],
    cache_path: Path,
    batch_size: int,
) -> np.ndarray:
    if cache_path.exists():
        cached = np.load(cache_path, allow_pickle=True)
        cached_paths = [str(path) for path in cached["paths"].tolist()]
        if cached_paths == image_paths:
            return cached["vectors"].astype(np.float32)
    vectors = encoder.encode_paths(image_paths, batch_size=batch_size)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_path, paths=np.asarray(image_paths), vectors=vectors)
    return vectors


def normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def safe_model_id(model_id: str) -> str:
    return model_id.replace("/", "__").replace(":", "_")


def compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Le Reve Visual Backbone Ablation {payload['cases']}",
        "",
        f"- Run ID: `{payload['run_id']}`",
        f"- Created: `{payload['created_at']}`",
        f"- Catalog: `{payload['catalog']}`",
        f"- Eval: `{payload['eval']}`",
        f"- Products: **{payload['products']}**",
        f"- Cases: **{payload['cases']}**",
        "",
        "## Main Table",
        "",
        "| Model | Method | Top-1 | Top-5 | Wrong Category | Accepted Exact | Accepted Precision | Wrong Exact / All |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model_key, result in payload["models"].items():
        if result.get("error"):
            lines.append(f"| `{model_key}` | error |  |  |  |  |  | `{result['error']}` |")
            continue
        for method, method_result in result["methods"].items():
            m = method_result["metrics"]
            lines.append(
                f"| `{model_key}` | `{method}` | {m['top1_accuracy']:.1%} | {m['top5_recall']:.1%} | "
                f"{m['wrong_category_top1_rate']:.1%} | {m['accepted_exact_rate']:.1%} | "
                f"{m['accepted_exact_precision']:.1%} | {m['accepted_wrong_exact_rate']:.1%} |"
            )
    lines.extend(["", "## Model Notes", ""])
    for model_key, result in payload["models"].items():
        lines.append(f"- `{model_key}`: {result.get('model_id')} — {result.get('note', '')}")
        if result.get("error"):
            lines.append(f"  - Error: `{result['error']}`")
    return "\n".join(lines).rstrip() + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def print_model_summary(model_key: str, result: dict[str, Any]) -> None:
    if result.get("error"):
        print(f"  {model_key}: ERROR {result['error']}")
        return
    parts = []
    for method in ("visual_only", "visual_metadata", "cif_guarded"):
        metrics = result["methods"][method]["metrics"]
        parts.append(
            f"{method} top1={metrics['top1_accuracy']:.1%} top5={metrics['top5_recall']:.1%}"
        )
    print(f"  {model_key}: " + " | ".join(parts))


if __name__ == "__main__":
    raise SystemExit(main())
