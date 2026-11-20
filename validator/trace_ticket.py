from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


def load_classes(path: Path) -> dict[str, int]:
    """Map class name to YOLO class_id from classes.txt."""
    name_to_id: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            name_to_id[parts[1].strip().lower()] = int(parts[0])
    if not name_to_id:
        raise ValueError("classes.txt contains no classes")
    return name_to_id


def parse_version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def detect_guideline_and_class(
    changelog_text: str, ticket_text: str, name_to_id: dict[str, int]
) -> tuple[str, int]:
    """Extract the newest guideline version and the changed class_id."""
    versions = re.findall(r"^##\s*(v\d+(?:\.\d+)*)\b", changelog_text, flags=re.MULTILINE)
    if not versions:
        versions = re.findall(r"\bv\d+(?:\.\d+)+\b", changelog_text)
    if not versions:
        raise ValueError("Cannot find guideline versions in changelog.md")
    latest_version = max(set(versions), key=parse_version_tuple)

    candidates = re.findall(r"`([^`]+)`", changelog_text) + re.findall(r"`([^`]+)`", ticket_text)
    for cand in candidates:
        key = cand.strip().lower()
        if key in name_to_id:
            return latest_version, name_to_id[key]

    combined = f"{changelog_text}\n{ticket_text}".lower()
    for name in sorted(name_to_id, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", combined):
            return latest_version, name_to_id[name]

    raise ValueError("Cannot determine target class from changelog.md or ticket.md")


def load_jobs(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return {row["job_id"].strip(): row for row in csv.DictReader(stream)}


def label_has_class(label_path: Path, target_class_id: int) -> bool:
    if not label_path.is_file():
        return False
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            if int(parts[0]) == target_class_id:
                return True
        except ValueError:
            continue
    return False


def build_trace(delivery: Path) -> dict[str, list[str]]:
    name_to_id = load_classes(delivery / "classes.txt")
    ticket_text = (delivery / "incoming" / "ticket.md").read_text(encoding="utf-8")
    changelog_text = (delivery / "guideline" / "changelog.md").read_text(encoding="utf-8")

    reported_scenes = set(re.findall(r"\bscene_[A-Za-z0-9_]+\b", ticket_text))
    latest_version, target_class_id = detect_guideline_and_class(
        changelog_text, ticket_text, name_to_id
    )
    jobs = load_jobs(delivery / "jobs.csv")

    metadata: dict[str, Any] = json.loads((delivery / "metadata.json").read_text(encoding="utf-8"))
    manifest_labels: dict[str, Path] = {}
    manifest_path = delivery / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_items = manifest.get("items", {})
        if isinstance(manifest_items, dict):
            for key, item in manifest_items.items():
                stem = Path(key).stem
                if isinstance(item, dict) and item.get("label"):
                    manifest_labels[stem] = delivery / item["label"]
        elif isinstance(manifest_items, list):
            for item in manifest_items:
                stem = Path(item["image"]).stem
                if item.get("label"):
                    manifest_labels[stem] = delivery / item["label"]

    tier_a: set[str] = set()
    tier_b: set[str] = set()
    notify: set[str] = set()

    for item in metadata.get("items", []):
        image_stem = Path(item["image"]).stem
        scene_id = item["scene_id"].strip()
        job_id = item["job_id"].strip()
        job = jobs.get(job_id)
        if job is None:
            continue

        # Always use job-level guideline from jobs.csv (not metadata.json).
        if job["guideline"].strip() == latest_version:
            continue

        label_path = manifest_labels.get(image_stem, delivery / "labels" / f"{image_stem}.txt")
        if not label_has_class(label_path, target_class_id):
            continue

        if scene_id in reported_scenes:
            tier_a.add(image_stem)
        else:
            tier_b.add(image_stem)

        if job.get("annotator"):
            notify.add(job["annotator"].strip())
        if job.get("reviewer"):
            notify.add(job["reviewer"].strip())

    return {
        "tier_a": sorted(tier_a),
        "tier_b": sorted(tier_b),
        "notify": sorted(notify),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Trace AI ticket to tier_a, tier_b, and notify.")
    parser.add_argument("delivery", type=Path, help="delivery directory to inspect")
    parser.add_argument("--out", required=True, type=Path, help="output path for trace.json")
    args = parser.parse_args()

    delivery = args.delivery.resolve()
    if not delivery.is_dir():
        parser.error(f"delivery directory does not exist: {delivery}")

    trace = build_trace(delivery)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Ghi trace.json -> {args.out} "
        f"(tier_a={len(trace['tier_a'])}, tier_b={len(trace['tier_b'])}, notify={len(trace['notify'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
