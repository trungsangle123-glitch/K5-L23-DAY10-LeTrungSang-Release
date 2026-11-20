"""Render candidate overlays for human review. Pillow is allowed in this viewer.

The validator itself remains standard-library-only; this file is only a visual aid.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


COLORS = {
    "class_disagreement": (231, 76, 60),
    "bbox_drift": (243, 156, 18),
    "missing_box": (52, 152, 219),
    "instance_merge": (155, 89, 182),
}
# Màu riêng cho từng segment ứng viên trong cùng ảnh (tránh vàng/cyan đang dùng cho box detection).
SEGMENT_PALETTE = [
    (230, 25, 75), (60, 180, 75), (145, 30, 180), (245, 130, 48), (0, 130, 200),
    (240, 50, 230), (128, 0, 0), (170, 110, 40), (0, 128, 128), (128, 128, 0),
    (250, 190, 212), (0, 0, 128),
]
TYPE_SHORT = {
    "class_disagreement": "CLS",
    "bbox_drift": "DRIFT",
    "missing_box": "MISS",
    "instance_merge": "MERGE",
}


def read_classes(path: Path) -> dict[int, str]:
    classes = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            try:
                classes[int(parts[0])] = parts[1].strip()
            except ValueError:
                continue
    return classes


def parse_boxes(path: Path, width: int, height: int, classes: dict[int, str]) -> list[dict]:
    result = []
    if not path.is_file():
        return result
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        parts = line.split()
        if len(parts) != 5:
            continue
        try:
            class_id = int(parts[0])
            xc, yc, box_w, box_h = map(float, parts[1:])
        except ValueError:
            continue
        if class_id not in classes or not all(math.isfinite(value) for value in (xc, yc, box_w, box_h)):
            continue
        result.append(
            {
                "class_name": classes[class_id],
                "bbox": (
                    (xc - box_w / 2) * width,
                    (yc - box_h / 2) * height,
                    (xc + box_w / 2) * width,
                    (yc + box_h / 2) * height,
                ),
                "index": index,
            }
        )
    return result


def safe_delivery_path(delivery: Path, relative: str) -> Path:
    root = delivery.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"Delivery path escapes its directory: {relative}")
    return path


def boxes_for_candidate(candidate: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    boxes = []
    for evidence in candidate.get("evidence", []):
        detection = evidence.get("detection")
        if detection and detection.get("bbox_xyxy"):
            boxes.append(tuple(map(float, detection["bbox_xyxy"])))
        for pair in evidence.get("supporting_detection_pairs", []):
            if pair.get("bbox_xyxy"):
                boxes.append(tuple(map(float, pair["bbox_xyxy"])))
            partner = pair.get("partner", {})
            if partner.get("bbox_xyxy"):
                boxes.append(tuple(map(float, partner["bbox_xyxy"])))
    return boxes


def render_one(
    delivery: Path,
    stem: str,
    manifest_item: dict[str, Any],
    image_row: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
    class_names: dict[int, str],
    out_path: Path,
) -> None:
    width, height = int(image_row["width"]), int(image_row["height"])
    image_path = safe_delivery_path(delivery, manifest_item["image"])
    mask_path = safe_delivery_path(delivery, manifest_item["mask"])
    label_path = safe_delivery_path(delivery, manifest_item["label"])
    base = Image.open(image_path).convert("RGBA")
    if base.size != (width, height):
        width, height = base.size

    # Mỗi segment ứng viên một màu riêng (không tô chung một màu theo loại ứng viên), để các
    # segment nằm sát nhau không trông như một mảng liền (ca 000000015335 ở seed 34).
    segments: dict[int, dict[str, Any]] = {}
    highlighted_boxes: list[tuple[float, float, float, float]] = []
    for candidate in candidate_rows:
        for evidence in candidate.get("evidence", []):
            panoptic = evidence.get("panoptic", {})
            if panoptic.get("segment_id") is not None:
                segment_id = int(panoptic["segment_id"])
                if segment_id not in segments:
                    segments[segment_id] = {
                        "color": SEGMENT_PALETTE[len(segments) % len(SEGMENT_PALETTE)],
                        "type": candidate["candidate_type"],
                        "category": panoptic.get("category_name", "?"),
                    }
            highlighted_boxes.extend(boxes_for_candidate({"evidence": [evidence]}))

    mask_image = Image.open(mask_path).convert("RGB")
    if mask_image.size != (width, height):
        raise ValueError(f"Image/mask size mismatch for {stem}: {base.size} vs {mask_image.size}")
    mask_pixels = mask_image.load()
    # Đọc id segment của từng pixel một lần; đếm pixel và khung của từng segment ứng viên.
    ids = [[0] * width for _ in range(height)]
    for y in range(height):
        row = ids[y]
        for x in range(width):
            red, green, blue = mask_pixels[x, y]
            segment_id = red + green * 256 + blue * 65536
            row[x] = segment_id
            info = segments.get(segment_id)
            if info is not None:
                info["pixels"] = info.get("pixels", 0) + 1
                x0, y0, x1, y1 = info.get("bbox", (x, y, x, y))
                info["bbox"] = (min(x0, x), min(y0, y), max(x1, x), max(y1, y))

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay_pixels = overlay.load()
    for y in range(height):
        for x in range(width):
            info = segments.get(ids[y][x])
            if info is None:
                continue
            # Viền: pixel có hàng xóm (trên/dưới/trái/phải) thuộc segment khác hoặc nằm ở mép ảnh.
            sid = ids[y][x]
            edge = (
                x == 0 or y == 0 or x == width - 1 or y == height - 1
                or ids[y][x - 1] != sid or ids[y][x + 1] != sid
                or ids[y - 1][x] != sid or ids[y + 1][x] != sid
            )
            overlay_pixels[x, y] = (255, 255, 255, 255) if edge else (*info["color"], 120)
    base = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(base)
    detections = parse_boxes(label_path, width, height, class_names)
    for detection in detections:
        box = detection["bbox"]
        is_candidate_box = any(
            all(abs(box[index] - target[index]) < 0.1 for index in range(4))
            for target in highlighted_boxes
        )
        color = (255, 215, 0, 255) if is_candidate_box else (0, 220, 255, 220)
        draw.rectangle(box, outline=color, width=4 if is_candidate_box else 2)
        label = f"{detection['class_name']} #{detection['index']}"
        draw.text((box[0] + 2, max(0, box[1] - 13)), label, fill=color, stroke_width=1, stroke_fill=(0, 0, 0, 220))

    # Số hiệu S1, S2... đặt giữa mỗi segment (vẽ sau box để không bị che).
    shown = [(sid, info) for sid, info in segments.items() if "bbox" in info]
    for number, (_, info) in enumerate(shown, start=1):
        x0, y0, x1, y1 = info["bbox"]
        draw.text(((x0 + x1) / 2 - 6, (y0 + y1) / 2 - 6), f"S{number}", fill=(255, 255, 255, 255),
                  stroke_width=2, stroke_fill=(*info["color"], 255))

    legend = "  |  ".join(
        f"{candidate['candidate_type']} ({candidate['evidence_count']})"
        for candidate in candidate_rows
    )
    draw.rectangle((0, 0, width, 24), fill=(0, 0, 0, 190))
    draw.text((6, 5), f"{stem}: {legend}", fill=(255, 255, 255, 255), font=ImageFont.load_default())

    # Dải chú thích ở đáy: mỗi segment một dòng "S1 MERGE person 2984px" (segment quá nhỏ khó phủ hai vật).
    line_h, per_row = 14, max(1, width // 210)
    rows_needed = (len(shown) + per_row - 1) // per_row
    canvas = Image.new("RGBA", (width, height + rows_needed * line_h + 6), (0, 0, 0, 255))
    canvas.paste(base, (0, 0))
    legend_draw = ImageDraw.Draw(canvas)
    for number, (_, info) in enumerate(shown, start=1):
        col, row = (number - 1) % per_row, (number - 1) // per_row
        text = f"S{number} {TYPE_SHORT.get(info['type'], info['type'])} {info['category']} {info['pixels']}px"
        legend_draw.rectangle((col * 210 + 4, height + 5 + row * line_h, col * 210 + 14, height + 15 + row * line_h),
                              fill=(*info["color"], 255), outline=(255, 255, 255, 255))
        legend_draw.text((col * 210 + 18, height + 4 + row * line_h), text, fill=(255, 255, 255, 255))
    if max(canvas.size) < 400:  # ảnh nhỏ (khoảng 240x320): phóng to 2 lần cho dễ nhìn
        canvas = canvas.resize((canvas.width * 2, canvas.height * 2), Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, quality=92)


def write_review_template(path: Path, candidates: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("image", "type", "verdict", "note"))
        writer.writeheader()
        for candidate in candidates:
            candidate_type = candidate["candidate_type"]
            writer.writerow(
                {
                    "image": candidate["image"],
                    "type": "" if candidate_type == "class_disagreement" else candidate_type,
                    "verdict": "",
                    "note": "",
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render candidate overlays for manual image review")
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="preview directory")
    args = parser.parse_args()
    delivery = args.delivery.resolve()
    candidate_data = json.loads(args.candidates.read_text(encoding="utf-8"))
    candidates = candidate_data.get("candidates", [])
    manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))["items"]
    manifest_by_stem = {Path(key).stem: item for key, item in manifest.items()}
    panoptic = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    image_rows = {Path(image["file_name"]).stem: image for image in panoptic.get("images", [])}
    class_names = read_classes(delivery / "classes.txt")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate["image"], []).append(candidate)

    args.out.mkdir(parents=True, exist_ok=True)
    rendered = []
    for stem, candidate_rows in sorted(grouped.items()):
        item = manifest_by_stem.get(stem)
        image_row = image_rows.get(stem)
        if not item or not image_row:
            continue
        file_name = f"{stem}.jpg"
        render_one(delivery, stem, item, image_row, candidate_rows, class_names, args.out / file_name)
        rendered.append((stem, candidate_rows, file_name))

    rows = []
    for stem, candidate_rows, file_name in rendered:
        types = ", ".join(candidate["candidate_type"] for candidate in candidate_rows)
        suggestions = "; ".join(
            ", ".join(candidate["suggested_error_types"])
            for candidate in candidate_rows
        )
        rows.append(
            f"<tr><td>{html.escape(stem)}</td><td>{html.escape(types)}</td>"
            f"<td>{html.escape(suggestions)}</td><td><a href='{html.escape(file_name)}'>"
            f"<img loading='lazy' width='320' src='{html.escape(file_name)}'></a></td></tr>"
        )
    page = (
        "<!doctype html><html><head><meta charset='utf-8'><title>Candidate review</title>"
        "<style>body{font:14px sans-serif;margin:24px}table{border-collapse:collapse}"
        "td,th{border:1px solid #bbb;padding:8px;vertical-align:top}th{position:sticky;top:0;background:#fff}"
        "img{height:auto}code{background:#eee;padding:2px 4px}</style></head><body>"
        "<h1>Review queue</h1><p>Cyan boxes are detections; yellow boxes are candidate matches. "
        "Each candidate segment has its own color with a white outline, labelled "
        "'TYPE category Npx' (CLS = class disagreement, DRIFT = bbox drift, MISS = missing box, "
        "MERGE = instance merge). Two people with separate outlines are two segments, not a merge. "
        "This page shows candidates only; confirm or reject after "
        "inspecting the image.</p><table><thead><tr><th>Image</th>"
        "<th>Candidate</th><th>Possible error type</th><th>Overlay</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></body></html>"
    )
    (args.out / "index.html").write_text(page, encoding="utf-8")
    write_review_template(args.out.parent / "review_log_template.csv", candidates)
    print(f"Rendered {len(rendered)} images into {args.out}")
    print(f"Index: {args.out / 'index.html'}")
    print(f"Review template: {args.out.parent / 'review_log_template.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
