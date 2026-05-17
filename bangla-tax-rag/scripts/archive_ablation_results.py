from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_ROOT = ROOT / "results" / "ablation_archive"
REPORT_PATTERNS = (
    "q1_image_research_pass_*.json",
    "q1_image_research_pass_*.md",
    "cif_rag_research_pass_*.json",
    "cif_rag_research_pass_*.md",
)
DATASET_PATHS = (
    ROOT / "evaluation" / "q1_image_search_research_set.jsonl",
    ROOT / "evaluation" / "cif_counterfactual_commerce_set.jsonl",
)
DOC_PATHS = (
    ROOT / "docs" / "q1_image_search_research_pipeline.md",
    ROOT / "docs" / "cif_rag_architecture_plan.md",
    ROOT / "learn_image.md",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive current image/CIF result artifacts for future ablations."
    )
    parser.add_argument("--label", default="baseline_cif_rag_mvp")
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument(
        "--latest-only",
        action="store_true",
        help="Archive only the latest Q1 and latest CIF pass instead of every matching report.",
    )
    args = parser.parse_args()

    created_at = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    safe_label = safe_name(args.label)
    archive_dir = Path(args.out_root) / f"{created_at}_{safe_label}"
    reports_dir = archive_dir / "reports"
    datasets_dir = archive_dir / "datasets"
    docs_dir = archive_dir / "docs"
    reports_dir.mkdir(parents=True, exist_ok=True)
    datasets_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    report_files = discover_reports(latest_only=args.latest_only)
    copied_reports = copy_files(report_files, reports_dir)
    copied_datasets = copy_files([path for path in DATASET_PATHS if path.exists()], datasets_dir)
    copied_docs = copy_files([path for path in DOC_PATHS if path.exists()], docs_dir)

    manifest = {
        "archive_id": archive_dir.name,
        "label": args.label,
        "created_at": datetime.now(UTC).isoformat(),
        "repo_root": str(ROOT),
        "git": git_snapshot(),
        "reports": copied_reports,
        "datasets": copied_datasets,
        "docs": copied_docs,
        "metrics": extract_metrics(report_files),
        "reproduction_commands": [
            ".venv/bin/python scripts/run_q1_image_research_pass.py --engine auto --methods full_system metadata_baseline no_identity_ablation policy_oracle naive_oracle_top1",
            ".venv/bin/python scripts/run_cif_rag_research_eval.py",
            f".venv/bin/python scripts/archive_ablation_results.py --label {safe_label}",
        ],
    }
    (archive_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (archive_dir / "README.md").write_text(render_readme(manifest), encoding="utf-8")
    update_index(Path(args.out_root), manifest)

    print(f"Ablation archive saved: {archive_dir}")
    print(f"  reports: {len(copied_reports)}")
    print(f"  datasets: {len(copied_datasets)}")
    print(f"  docs: {len(copied_docs)}")
    return 0


def discover_reports(*, latest_only: bool) -> list[Path]:
    reports: list[Path] = []
    for pattern in REPORT_PATTERNS:
        reports.extend(sorted((ROOT / "results").glob(pattern)))
    if not latest_only:
        return sorted(set(reports))

    latest: list[Path] = []
    for stem in ("q1_image_research_pass", "cif_rag_research_pass"):
        for suffix in ("json", "md"):
            matches = sorted((ROOT / "results").glob(f"{stem}_*.{suffix}"))
            if matches:
                latest.append(matches[-1])
    return sorted(set(latest))


def copy_files(paths: list[Path], target_dir: Path) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        target = target_dir / path.name
        shutil.copy2(path, target)
        copied.append(
            {
                "source": rel(path),
                "archive_path": rel(target),
                "bytes": target.stat().st_size,
            }
        )
    return copied


def extract_metrics(report_files: list[Path]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for path in sorted(report_files):
        if path.suffix != ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            metrics.append({"source": rel(path), "error": str(exc)})
            continue
        metrics.append(
            {
                "source": rel(path),
                "run_id": payload.get("run_id"),
                "created_at": payload.get("created_at"),
                "metrics": payload.get("metrics"),
                "methods": payload.get("methods"),
                "engine": payload.get("engine"),
            }
        )
    return metrics


def git_snapshot() -> dict[str, Any]:
    return {
        "branch": run_git(["branch", "--show-current"]),
        "head": run_git(["rev-parse", "HEAD"]),
        "status_short": run_git(["status", "--short"]),
    }


def run_git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception as exc:
        return f"git unavailable: {exc}"


def render_readme(manifest: dict[str, Any]) -> str:
    lines = [
        "# Ablation Archive",
        "",
        f"- Archive ID: `{manifest['archive_id']}`",
        f"- Label: `{manifest['label']}`",
        f"- Created: `{manifest['created_at']}`",
        f"- Branch: `{manifest['git'].get('branch')}`",
        f"- HEAD: `{manifest['git'].get('head')}`",
        "",
        "## Reports",
        "",
    ]
    for item in manifest["reports"]:
        lines.append(f"- `{item['archive_path']}` ({item['bytes']} bytes)")
    lines.extend(["", "## Datasets", ""])
    for item in manifest["datasets"]:
        lines.append(f"- `{item['archive_path']}` ({item['bytes']} bytes)")
    lines.extend(["", "## Docs", ""])
    for item in manifest["docs"]:
        lines.append(f"- `{item['archive_path']}` ({item['bytes']} bytes)")
    lines.extend(["", "## Metrics Snapshot", ""])
    for metric in manifest["metrics"]:
        lines.append(f"### `{metric['source']}`")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(metric.get("metrics"), indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")
    lines.extend(["## Reproduction Commands", "", "```bash"])
    lines.extend(manifest["reproduction_commands"])
    lines.extend(["```", ""])
    return "\n".join(lines)


def update_index(out_root: Path, manifest: dict[str, Any]) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    index_path = out_root / "README.md"
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else "# Ablation Archives\n\n"
    entry = (
        f"- [{manifest['archive_id']}](./{manifest['archive_id']}/README.md) "
        f"- `{manifest['label']}` - `{manifest['created_at']}`\n"
    )
    if entry not in existing:
        index_path.write_text(existing.rstrip() + "\n" + entry, encoding="utf-8")


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip().lower()).strip("_") or "archive"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
