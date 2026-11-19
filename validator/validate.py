from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import pngutil  # noqa: E402


RULE_TYPES = (
    "missing_image",
    "wrong_hash",
    "invalid_class",
    "bbox_out_of_bounds",
    "duplicate_box",
    "scene_leak",
    "guideline_mismatch",
    "invalid_category_id",
    "thing_overlap",
)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path.name}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def image_stem(value: str) -> str:
    return Path(value).stem


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def delivery_path(delivery: Path, relative: str) -> Path:
    """Resolve a manifest path while keeping reads inside delivery."""
    root = delivery.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"Manifest path escapes delivery: {relative}")
    return path


def parse_classes(path: Path) -> set[int]:
    # The lab's detection schema is fixed to class ids 0..79. Parse the file
    # too, so a missing/malformed required class map is reported clearly.
    ids: set[int] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        try:
            ids.add(int(parts[0]))
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Bad classes.txt row {line_number}: {line!r}") from exc
    if not ids:
        raise ValueError("classes.txt contains no class ids")
    return ids


def parse_yolo(path: Path) -> list[tuple[int, float, float, float, float]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"Bad YOLO row in {path.name}:{line_number}; expected 5 values")
        try:
            class_id = int(parts[0])
            x, y, width, height = map(float, parts[1:])
        except ValueError as exc:
            raise ValueError(f"Non-numeric YOLO row in {path.name}:{line_number}") from exc
        if not all(math.isfinite(number) for number in (x, y, width, height)):
            raise ValueError(f"Non-finite YOLO coordinate in {path.name}:{line_number}")
        rows.append((class_id, x, y, width, height))
    return rows


def has_duplicate_box(
    rows: list[tuple[int, float, float, float, float]], width: int, height: int
) -> bool:
    """A duplicate has the same class/size and centers within 1–2 pixels."""
    for index, first in enumerate(rows):
        c1, x1, y1, w1, h1 = first
        for c2, x2, y2, w2, h2 in rows[index + 1 :]:
            if c1 != c2:
                continue
            # The duplicate fault preserves normalized width and height exactly.
            # A tiny float tolerance accommodates harmless text formatting.
            if not math.isclose(w1, w2, rel_tol=0.0, abs_tol=1e-6):
                continue
            if not math.isclose(h1, h2, rel_tol=0.0, abs_tol=1e-6):
                continue
            dx, dy = abs(x1 - x2) * width, abs(y1 - y2) * height
            if max(dx, dy) <= 2.01 and max(dx, dy) > 0:
                return True
    return False


def collect_errors(delivery: Path) -> list[dict[str, str]]:
    manifest = read_json(delivery / "manifest.json").get("items", {})
    metadata_rows = read_json(delivery / "metadata.json").get("items", [])
    panoptic = read_json(delivery / "panoptic.json")
    jobs_rows = read_csv(delivery / "jobs.csv")
    valid_detection_ids = parse_classes(delivery / "classes.txt")

    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must contain an 'items' object")
    metadata = {row["image"]: row for row in metadata_rows}
    jobs = {row["job_id"]: row for row in jobs_rows}
    dimensions = {
        image["file_name"]: (int(image["width"]), int(image["height"]))
        for image in panoptic.get("images", [])
    }
    image_ids = {
        Path(image["file_name"]).stem: image["id"]
        for image in panoptic.get("images", [])
    }
    annotations = {annotation["image_id"]: annotation for annotation in panoptic.get("annotations", [])}
    valid_category_ids = {int(category["id"]) for category in panoptic.get("categories", [])}

    findings: set[tuple[str, str]] = set()
    scene_splits: dict[str, set[str]] = defaultdict(set)

    for key, item in manifest.items():
        name = image_stem(key)
        meta = metadata.get(key) or metadata.get(name)
        if meta is None:
            raise ValueError(f"No metadata entry for image {name}")
        scene_splits[str(meta["scene_id"])].add(str(meta["split"]))

        image_path = delivery_path(delivery, item["image"])
        if not image_path.is_file():
            findings.add(("missing_image", name))
        elif sha256(image_path) != item.get("image_sha256"):
            findings.add(("wrong_hash", name))

        job = jobs.get(str(meta["job_id"]))
        if job is None:
            raise ValueError(f"No jobs.csv entry for job {meta['job_id']}")
        if meta.get("guideline_version") != job.get("guideline"):
            findings.add(("guideline_mismatch", name))

        label_path = delivery_path(delivery, item["label"])
        if label_path.is_file():
            rows = parse_yolo(label_path)
            if any(class_id not in valid_detection_ids or not 0 <= class_id < 80 for class_id, *_ in rows):
                findings.add(("invalid_class", name))

            image_file = Path(item["image"]).name
            size = dimensions.get(image_file)
            if size is not None:
                width, height = size
                if any(
                    x - box_w / 2 < -0.01
                    or y - box_h / 2 < -0.01
                    or x + box_w / 2 > 1.01
                    or y + box_h / 2 > 1.01
                    for _, x, y, box_w, box_h in rows
                ):
                    findings.add(("bbox_out_of_bounds", name))
                if has_duplicate_box(rows, width, height):
                    findings.add(("duplicate_box", name))

        # Panoptic checks use its own image table and the supplied PNG mask.
        image_id = image_ids.get(name)
        annotation = annotations.get(image_id)
        if annotation is None:
            continue
        if any(int(segment["category_id"]) not in valid_category_ids for segment in annotation.get("segments_info", [])):
            findings.add(("invalid_category_id", name))

        mask_rel = item.get("mask")
        mask_path = delivery_path(delivery, mask_rel) if mask_rel else None
        if mask_path is not None and mask_path.is_file():
            _, _, pixels = pngutil.read_rgb(mask_path)
            actual_areas: Counter[int] = Counter()
            for offset in range(0, len(pixels), 3):
                segment_id = pngutil.segment_id(pixels, offset)
                if segment_id != 0:  # id 0 is the background
                    actual_areas[segment_id] += 1
            if any(
                int(segment["area"]) > actual_areas.get(int(segment["id"]), 0)
                for segment in annotation.get("segments_info", [])
            ):
                findings.add(("thing_overlap", name))

    for scene_id, splits in scene_splits.items():
        if len(splits) > 1:
            findings.add(("scene_leak", scene_id))

    return [
        {"type": kind, "target": target}
        for kind, target in sorted(findings, key=lambda pair: (RULE_TYPES.index(pair[0]), pair[1]))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Find rule-based errors in a delivery folder")
    parser.add_argument("delivery", type=Path, help="delivery directory to inspect")
    parser.add_argument("--out", required=True, type=Path, help="path for errors.json")
    # Reserved for the phase-2 interface. Phase 1 emits rule errors only.
    parser.add_argument("--candidates", type=Path, help="optional phase-2 candidates file (not used in phase 1)")
    args = parser.parse_args()
    delivery = args.delivery.resolve()
    if not delivery.is_dir():
        parser.error(f"delivery directory does not exist: {delivery}")

    try:
        errors = collect_errors(delivery)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"cannot validate delivery: {exc}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Ghi {len(errors)} phát hiện vào {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
