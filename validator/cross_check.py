"""Generate human-review candidates by comparing detection and panoptic labels.

This module only reads the delivery directory. It deliberately emits candidates,
not confirmed semantic errors; a person must inspect the image before deciding.
"""

from __future__ import annotations

import csv
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


# These are starting review thresholds, not claims that a label is wrong.
# The clean calibration run is used to assess and tune their noise level.
THRESHOLDS = {
    "pair_min_iou": 0.05,
    "pair_min_mask_coverage": 0.10,
    "class_disagreement_min_iou": 0.10,
    "class_disagreement_min_mask_coverage": 0.20,
    "bbox_drift_max_mask_coverage": 0.98,
    "bbox_drift_min_segment_pixels": 100,
    "missing_box_min_segment_pixels": 600,
    "missing_box_min_side_pixels": 15,
    "instance_merge_min_mask_coverage": 0.30,
    "instance_merge_min_overlap_pixels": 50,
    "instance_merge_min_box_mask_fraction": 0.03,
    "instance_merge_max_detection_iou": 0.10,
}


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path.name}")
    return value


def _inside_delivery(delivery: Path, relative: str) -> Path:
    root = delivery.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"Delivery path escapes its directory: {relative}")
    return path


def _class_names(path: Path) -> dict[int, str]:
    names: dict[int, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"Bad classes.txt row {line_number}: {line!r}")
        try:
            names[int(parts[0])] = parts[1].strip()
        except ValueError as exc:
            raise ValueError(f"Bad class id on classes.txt row {line_number}") from exc
    if not names:
        raise ValueError("classes.txt contains no class names")
    return names


def _yolo_boxes(path: Path, width: int, height: int, names: dict[int, str]) -> tuple[list[dict], int]:
    boxes: list[dict] = []
    skipped = 0
    if not path.is_file():
        return boxes, 0
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            skipped += 1
            continue
        try:
            class_id = int(parts[0])
            xc, yc, box_w, box_h = map(float, parts[1:])
        except ValueError:
            skipped += 1
            continue
        if class_id not in names or not all(math.isfinite(v) for v in (xc, yc, box_w, box_h)):
            skipped += 1
            continue
        x1, y1 = (xc - box_w / 2) * width, (yc - box_h / 2) * height
        x2, y2 = (xc + box_w / 2) * width, (yc + box_h / 2) * height
        px1 = max(0, min(width, math.floor(x1)))
        py1 = max(0, min(height, math.floor(y1)))
        px2 = max(0, min(width, math.ceil(x2)))
        py2 = max(0, min(height, math.ceil(y2)))
        if px2 <= px1 or py2 <= py1:
            skipped += 1
            continue
        boxes.append(
            {
                "index": index,
                "class_id": class_id,
                "class_name": names[class_id],
                "bbox": (x1, y1, x2, y2),
                "pixel_rect": (px1, py1, px2, py2),
            }
        )
    return boxes, skipped


def _xywh_to_xyxy(value: list[float]) -> tuple[float, float, float, float]:
    x, y, width, height = map(float, value)
    return x, y, x + width, y + height


def _iou(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_first = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    area_second = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = area_first + area_second - intersection
    return intersection / union if union > 0 else 0.0


def _box_mask_fraction(box: dict, overlap: int) -> float:
    """Fraction of a rasterized detection box occupied by one segment mask."""
    x1, y1, x2, y2 = box["pixel_rect"]
    box_area = max(0, x2 - x1) * max(0, y2 - y1)
    return overlap / box_area if box_area else 0.0


def _mask_measurements(
    pixels: bytearray,
    width: int,
    height: int,
    thing_segments: dict[int, dict],
    boxes: list[dict],
) -> tuple[Counter[int], dict[int, tuple[int, int, int, int]], Counter[tuple[int, int]]]:
    """Scan the mask as horizontal runs and count segment pixels inside each box."""
    areas: Counter[int] = Counter()
    bounds: dict[int, list[int]] = {}
    overlaps: Counter[tuple[int, int]] = Counter()

    active_by_row: list[list[dict]] = [[] for _ in range(height)]
    for box in boxes:
        _, y1, _, y2 = box["pixel_rect"]
        for y in range(y1, y2):
            active_by_row[y].append(box)

    for y in range(height):
        row_boxes = active_by_row[y]
        row_offset = y * width * 3
        run_id = None
        run_start = 0
        for x in range(width + 1):
            if x == width:
                segment_id = None
            else:
                offset = row_offset + x * 3
                segment_id = pixels[offset] + pixels[offset + 1] * 256 + pixels[offset + 2] * 65536

            if segment_id == run_id:
                continue

            if run_id in thing_segments:
                run_length = x - run_start
                areas[run_id] += run_length
                box = bounds.get(run_id)
                if box is None:
                    bounds[run_id] = [run_start, y, x, y + 1]
                else:
                    box[0] = min(box[0], run_start)
                    box[1] = min(box[1], y)
                    box[2] = max(box[2], x)
                    box[3] = max(box[3], y + 1)

                for detection in row_boxes:
                    dx1, _, dx2, _ = detection["pixel_rect"]
                    overlap = max(0, min(x, dx2) - max(run_start, dx1))
                    if overlap:
                        overlaps[(run_id, detection["index"])] += overlap

            run_id = segment_id
            run_start = x

    frozen_bounds = {segment_id: tuple(value) for segment_id, value in bounds.items()}
    return areas, frozen_bounds, overlaps


def _candidate_evidence(box: dict, segment: dict, iou: float, coverage: float, overlap: int, area: int) -> dict:
    return {
        "detection": {
            "class_id": box["class_id"],
            "class_name": box["class_name"],
            "bbox_xyxy": [round(value, 2) for value in box["bbox"]],
        },
        "panoptic": {
            "segment_id": segment["id"],
            "category_id": segment["category_id"],
            "category_name": segment["category_name"],
            "mask_bbox_xyxy": list(segment["mask_bbox"]),
        },
        "bbox_iou": round(iou, 4),
        "mask_coverage": round(coverage, 4),
        "overlap_pixels": overlap,
        "segment_pixels": area,
    }


def generate_candidates(delivery: Path) -> dict[str, Any]:
    """Return raw review candidates and calibration counts for one delivery."""
    delivery = delivery.resolve()
    manifest_doc = _read_json(delivery / "manifest.json")
    panoptic = _read_json(delivery / "panoptic.json")
    class_names = _class_names(delivery / "classes.txt")
    categories = {
        int(category["id"]): category
        for category in panoptic.get("categories", [])
    }
    image_rows = {
        Path(image["file_name"]).stem: image
        for image in panoptic.get("images", [])
    }
    annotation_rows = {
        int(annotation["image_id"]): annotation
        for annotation in panoptic.get("annotations", [])
    }
    manifest_rows = {
        Path(key).stem: item
        for key, item in manifest_doc.get("items", {}).items()
    }

    candidate_evidence: dict[tuple[str, str], list[dict]] = defaultdict(list)
    skipped_missing_image = 0
    skipped_mask = 0
    skipped_bad_boxes = 0
    images_checked = 0

    for stem, item in sorted(manifest_rows.items()):
        image_path = _inside_delivery(delivery, item["image"])
        if not image_path.is_file():
            # A missing image cannot be visually reviewed; the rule validator reports it.
            skipped_missing_image += 1
            continue

        image_row = image_rows.get(stem)
        if image_row is None:
            continue
        image_id = int(image_row["id"])
        annotation = annotation_rows.get(image_id)
        if annotation is None:
            continue
        width, height = int(image_row["width"]), int(image_row["height"])
        label_path = _inside_delivery(delivery, item["label"])
        boxes, bad_boxes = _yolo_boxes(label_path, width, height, class_names)
        skipped_bad_boxes += bad_boxes

        segments: dict[int, dict] = {}
        for raw in annotation.get("segments_info", []):
            category_id = int(raw["category_id"])
            category = categories.get(category_id)
            if category is None or not category.get("isthing") or raw.get("iscrowd"):
                continue
            segments[int(raw["id"])] = {
                "id": int(raw["id"]),
                "category_id": category_id,
                "category_name": str(category["name"]),
            }

        mask_relative = item.get("mask")
        mask_path = _inside_delivery(delivery, mask_relative) if mask_relative else None
        if mask_path is None or not mask_path.is_file():
            skipped_mask += 1
            continue
        mask_width, mask_height, pixels = pngutil.read_rgb(mask_path)
        if (mask_width, mask_height) != (width, height):
            skipped_mask += 1
            continue

        areas, bounds, overlaps = _mask_measurements(pixels, width, height, segments, boxes)
        images_checked += 1

        live_segments: dict[int, dict] = {}
        for segment_id, segment in segments.items():
            area = areas.get(segment_id, 0)
            mask_bbox = bounds.get(segment_id)
            if area and mask_bbox:
                live_segments[segment_id] = {**segment, "area": area, "mask_bbox": mask_bbox}

        pair_rows: list[dict] = []
        for segment_id, segment in live_segments.items():
            seg_bbox = tuple(map(float, segment["mask_bbox"]))
            area = segment["area"]
            for box in boxes:
                overlap = overlaps.get((segment_id, box["index"]), 0)
                coverage = overlap / area if area else 0.0
                iou = _iou(box["bbox"], seg_bbox)
                if iou >= THRESHOLDS["pair_min_iou"] or coverage >= THRESHOLDS["pair_min_mask_coverage"]:
                    pair_rows.append(
                        {
                            "segment": segment,
                            "box": box,
                            "iou": iou,
                            "coverage": coverage,
                            "overlap": overlap,
                        }
                    )

        # Greedy one-to-one matching by geometry; class name is compared only after matching.
        pair_rows.sort(
            key=lambda row: (
                max(row["iou"], row["coverage"] * 0.8),
                row["iou"],
                row["coverage"],
            ),
            reverse=True,
        )
        matched_segments: set[int] = set()
        matched_boxes: set[int] = set()
        matches: list[dict] = []
        for row in pair_rows:
            segment_id = row["segment"]["id"]
            box_id = row["box"]["index"]
            if segment_id in matched_segments or box_id in matched_boxes:
                continue
            matched_segments.add(segment_id)
            matched_boxes.add(box_id)
            matches.append(row)

        for row in matches:
            segment, box = row["segment"], row["box"]
            evidence = _candidate_evidence(
                box, segment, row["iou"], row["coverage"], row["overlap"], segment["area"]
            )
            if box["class_name"].casefold() != segment["category_name"].casefold():
                if (
                    row["iou"] >= THRESHOLDS["class_disagreement_min_iou"]
                    or row["coverage"] >= THRESHOLDS["class_disagreement_min_mask_coverage"]
                ):
                    evidence["possible_error_types"] = ["class_swap", "category_swap"]
                    candidate_evidence[(stem, "class_disagreement")].append(evidence)
            elif (
                segment["area"] >= THRESHOLDS["bbox_drift_min_segment_pixels"]
                and row["coverage"] < THRESHOLDS["bbox_drift_max_mask_coverage"]
            ):
                candidate_evidence[(stem, "bbox_drift")].append(evidence)

        # Significant thing segments with no spatially supported detection are missing-box candidates.
        for segment_id, segment in live_segments.items():
            if segment_id in matched_segments:
                continue
            x1, y1, x2, y2 = segment["mask_bbox"]
            if (
                segment["area"] < THRESHOLDS["missing_box_min_segment_pixels"]
                or min(x2 - x1, y2 - y1) < THRESHOLDS["missing_box_min_side_pixels"]
            ):
                continue
            nearest = None
            nearest_iou = 0.0
            for box in boxes:
                iou = _iou(box["bbox"], tuple(map(float, segment["mask_bbox"])))
                if iou > nearest_iou:
                    nearest, nearest_iou = box, iou
            candidate_evidence[(stem, "missing_box")].append(
                {
                    "panoptic": {
                        "segment_id": segment_id,
                        "category_id": segment["category_id"],
                        "category_name": segment["category_name"],
                        "mask_bbox_xyxy": list(segment["mask_bbox"]),
                    },
                    "segment_pixels": segment["area"],
                    "nearest_detection_iou": round(nearest_iou, 4),
                    "nearest_detection_class": nearest["class_name"] if nearest else None,
                }
            )

        # Require two distinct, same-class boxes. Highly overlapping COCO boxes can
        # naturally cover the same instance and otherwise swamp the clean queue.
        for segment_id, segment in live_segments.items():
            supporting: list[dict] = []
            for box in boxes:
                if box["class_name"].casefold() != segment["category_name"].casefold():
                    continue
                overlap = overlaps.get((segment_id, box["index"]), 0)
                coverage = overlap / segment["area"] if segment["area"] else 0.0
                box_mask_fraction = _box_mask_fraction(box, overlap)
                if (
                    overlap >= THRESHOLDS["instance_merge_min_overlap_pixels"]
                    and coverage >= THRESHOLDS["instance_merge_min_mask_coverage"]
                    and box_mask_fraction >= THRESHOLDS["instance_merge_min_box_mask_fraction"]
                ):
                    supporting.append(
                        {
                            "box_index": box["index"],
                            "class_id": box["class_id"],
                            "class_name": box["class_name"],
                            "bbox": box["bbox"],
                            "bbox_xyxy": [round(value, 2) for value in box["bbox"]],
                            "mask_pixels_in_box": overlap,
                            "segment_coverage": round(coverage, 4),
                            "box_mask_fraction": round(box_mask_fraction, 4),
                        }
                    )
            distinct_pairs = []
            for index, first in enumerate(supporting):
                for second in supporting[index + 1 :]:
                    detection_iou = _iou(first["bbox"], second["bbox"])
                    if detection_iou <= THRESHOLDS["instance_merge_max_detection_iou"]:
                        distinct_pairs.append(
                            {
                                key: value for key, value in first.items() if key != "bbox"
                            }
                            | {
                                "partner": {
                                    key: value for key, value in second.items() if key != "bbox"
                                },
                                "detection_iou": round(detection_iou, 4),
                            }
                        )
            if distinct_pairs:
                candidate_evidence[(stem, "instance_merge")].append(
                    {
                        "panoptic": {
                            "segment_id": segment_id,
                            "category_id": segment["category_id"],
                            "category_name": segment["category_name"],
                            "mask_bbox_xyxy": list(segment["mask_bbox"]),
                        },
                        "segment_pixels": segment["area"],
                        "supporting_detection_pairs": distinct_pairs,
                    }
                )

    candidates = []
    for (image, candidate_type), evidence in sorted(candidate_evidence.items()):
        suggested = ["class_swap", "category_swap"] if candidate_type == "class_disagreement" else [candidate_type]
        candidates.append(
            {
                "image": image,
                "candidate_type": candidate_type,
                "suggested_error_types": suggested,
                "evidence_count": len(evidence),
                "evidence": evidence,
            }
        )

    by_type = Counter(candidate["candidate_type"] for candidate in candidates)
    return {
        "summary": {
            "images_checked": images_checked,
            "candidate_rows": len(candidates),
            "unique_candidate_images": len({candidate["image"] for candidate in candidates}),
            "by_candidate_type": dict(sorted(by_type.items())),
            "skipped_missing_images": skipped_missing_image,
            "skipped_masks": skipped_mask,
            "skipped_bad_yolo_rows": skipped_bad_boxes,
            "thresholds": THRESHOLDS,
            "manual_review_required": True,
        },
        "candidates": candidates,
    }


def write_candidate_csv(path: Path, result: dict[str, Any]) -> None:
    """Write a compact companion queue so people can divide image review."""
    csv_path = path.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("image", "candidate_type", "suggested_error_types", "evidence_count", "evidence_summary"),
        )
        writer.writeheader()
        for candidate in result["candidates"]:
            evidence = candidate["evidence"]
            if candidate["candidate_type"] == "class_disagreement" and evidence:
                first = evidence[0]
                summary = (
                    f"detection={first['detection']['class_name']}; "
                    f"panoptic={first['panoptic']['category_name']}; "
                    f"IoU={first['bbox_iou']}; mask_coverage={first['mask_coverage']}"
                )
            elif candidate["candidate_type"] == "bbox_drift" and evidence:
                first = evidence[0]
                summary = (
                    f"class={first['detection']['class_name']}; "
                    f"IoU={first['bbox_iou']}; mask_coverage={first['mask_coverage']}"
                )
            elif candidate["candidate_type"] == "missing_box" and evidence:
                first = evidence[0]
                summary = (
                    f"panoptic={first['panoptic']['category_name']}; "
                    f"pixels={first['segment_pixels']}; "
                    f"nearest_IoU={first['nearest_detection_iou']}"
                )
            elif candidate["candidate_type"] == "instance_merge" and evidence:
                first = evidence[0]
                summary = (
                    f"panoptic={first['panoptic']['category_name']}; "
                    f"distinct_box_pairs={len(first['supporting_detection_pairs'])}"
                )
            else:
                summary = ""
            writer.writerow(
                {
                    "image": candidate["image"],
                    "candidate_type": candidate["candidate_type"],
                    "suggested_error_types": ";".join(candidate["suggested_error_types"]),
                    "evidence_count": candidate["evidence_count"],
                    "evidence_summary": summary,
                }
            )
