from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

DET_REWORK = {
    "missing_image",
    "invalid_class",
    "bbox_out_of_bounds",
    "duplicate_box",
    "class_swap",
    "bbox_drift",
    "missing_box",
}
PANOPTIC_ONLY = {
    "invalid_category_id",
    "thing_overlap",
    "category_swap",
    "instance_merge",
}
THRESHOLD = 0.02


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_valid_jpeg(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 4:
        return False
    data = path.read_bytes()
    return data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_classes(path: Path) -> dict[int, str]:
    classes: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        cid, name = line.split(maxsplit=1)
        classes[int(cid)] = name.strip()
    return classes


def build_handover(run_dir: Path) -> Path:
    run_dir = run_dir.resolve()
    delivery = run_dir / "delivery"
    rid = json.loads((delivery / "release.json").read_text(encoding="utf-8"))["release_id"]
    man_items: dict[str, dict[str, str]] = json.loads(
        (delivery / "manifest.json").read_text(encoding="utf-8")
    )["items"]
    meta_items: dict[str, dict[str, str]] = {
        m["image"]: m
        for m in json.loads((delivery / "metadata.json").read_text(encoding="utf-8"))["items"]
    }
    jobs = {row["job_id"]: row for row in read_csv(delivery / "jobs.csv")}
    classes = parse_classes(delivery / "classes.txt")
    errors: list[dict[str, str]] = json.loads(
        (run_dir / "errors.json").read_text(encoding="utf-8")
    )["errors"]

    # Determine rework images, fixed-in-v2 items, and panoptic-only items.
    rework_rows: list[dict[str, str]] = []
    rework_images: set[str] = set()
    panoptic_notes: list[str] = []
    wrong_hash_fixed: list[str] = []
    guideline_fixed: list[str] = []
    leaked_scenes: set[str] = set()

    for err in errors:
        etype = err["type"]
        target = err["target"]
        if etype == "scene_leak":
            leaked_scenes.add(target)
            continue
        if etype in DET_REWORK:
            if target not in rework_images:
                rework_images.add(target)
                m = meta_items.get(target, {})
                job = jobs.get(m.get("job_id", ""), {})
                rework_rows.append(
                    {
                        "image": target,
                        "type": etype,
                        "annotator": job.get("annotator", ""),
                        "reviewer": job.get("reviewer", ""),
                        "action": "reannotate_detection",
                    }
                )
        elif etype == "wrong_hash":
            img_path = delivery / man_items[target]["image"]
            if is_valid_jpeg(img_path):
                wrong_hash_fixed.append(target)
            elif target not in rework_images:
                rework_images.add(target)
                m = meta_items.get(target, {})
                job = jobs.get(m.get("job_id", ""), {})
                rework_rows.append(
                    {
                        "image": target,
                        "type": etype,
                        "annotator": job.get("annotator", ""),
                        "reviewer": job.get("reviewer", ""),
                        "action": "replace_corrupt_image",
                    }
                )
        elif etype == "guideline_mismatch":
            guideline_fixed.append(target)
        elif etype in PANOPTIC_ONLY:
            panoptic_notes.append(f"{target} ({etype})")

    # Resolve scene_leak splits by majority split per scene_id.
    scene_split_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for stem, m in meta_items.items():
        if stem not in rework_images:
            scene_split_counts[m["scene_id"]][m["split"]] += 1
    canonical_scene_split = {
        sc: cnt.most_common(1)[0][0] for sc, cnt in scene_split_counts.items()
    }

    v2_dir = run_dir / "handover" / f"{rid}_v2"
    if v2_dir.exists():
        shutil.rmtree(v2_dir)
    (v2_dir / "images").mkdir(parents=True, exist_ok=True)
    (v2_dir / "labels").mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, str]] = []
    truyvet_rows: list[dict[str, str]] = []
    label_counts: Counter[str] = Counter()

    for stem in sorted(man_items):
        if stem in rework_images:
            continue
        src_img = delivery / man_items[stem]["image"]
        src_lbl = delivery / man_items[stem]["label"]
        dst_img = v2_dir / "images" / f"{stem}.jpg"
        dst_lbl = v2_dir / "labels" / f"{stem}.txt"
        shutil.copy2(src_img, dst_img)
        shutil.copy2(src_lbl, dst_lbl)

        manifest_rows.append({"file": f"images/{stem}.jpg", "sha256": sha256_file(dst_img)})
        manifest_rows.append({"file": f"labels/{stem}.txt", "sha256": sha256_file(dst_lbl)})

        for line in dst_lbl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            cid = int(float(line.split()[0]))
            label_counts[classes.get(cid, str(cid))] += 1

        m = meta_items[stem]
        job = jobs[m["job_id"]]
        split = (
            canonical_scene_split[m["scene_id"]]
            if m["scene_id"] in leaked_scenes
            else m["split"]
        )
        truyvet_rows.append(
            {
                "image": stem,
                "scene_id": m["scene_id"],
                "split": split,
                "job_id": m["job_id"],
                "annotator": job["annotator"],
                "reviewer": job["reviewer"],
                "guideline": job["guideline"],
            }
        )

    write_csv(
        v2_dir / "rework_queue.csv",
        ["image", "type", "annotator", "reviewer", "action"],
        sorted(rework_rows, key=lambda r: (r["image"], r["type"])),
    )
    write_csv(
        v2_dir / "manifest.csv",
        ["file", "sha256"],
        sorted(manifest_rows, key=lambda r: r["file"]),
    )

    summary_rows = [
        {"class": cls_name, "count": cnt}
        for cls_name, cnt in sorted(label_counts.items())
    ]
    total_labels = sum(label_counts.values())
    summary_rows.append({"class": "TOTAL", "count": total_labels})
    write_csv(v2_dir / "label_summary.csv", ["class", "count"], summary_rows)

    write_csv(
        v2_dir / "truyvet.csv",
        ["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"],
        truyvet_rows,
    )

    # Summarize guideline versions by job.
    by_guide: dict[str, list[str]] = defaultdict(list)
    for jid, jrow in sorted(jobs.items()):
        by_guide[jrow["guideline"]].append(jid)
    guide_desc = ", ".join(
        f"{g} ({jids[0]}-{jids[-1]})" if len(jids) > 1 else f"{g} ({jids[0]})"
        for g, jids in sorted(by_guide.items())
    )

    err_targets = {e["target"] for e in errors}
    total_v1 = len(man_items)
    rate = len(err_targets) / total_v1
    v1_status = "Hold" if rate > THRESHOLD else "Release"
    n_v2 = len(truyvet_rows)

    readme_text = "\n".join(
        [
            f"Release: {rid}_v2",
            f"Parent: {rid}",
            f"Số ảnh: {n_v2}",
            f"Số nhãn: {total_labels}",
            f"Guideline: {guide_desc}",
            f"QC v1: {len(err_targets)}/{total_v1} = {rate:.1%}",
            f"Kết luận v1: {v1_status} — Tỉ lệ lỗi {rate:.1%} vượt ngưỡng 2%, không phát hành v1.",
            f"Kết luận v2: Release — Đã tách {len(rework_images)} ảnh lỗi detection/thiếu file vào rework_queue.csv; sửa metadata và giữ {n_v2} ảnh sạch detection.",
            (
                f"Ghi chú: Đã mở kiểm tra ảnh wrong_hash ({', '.join(sorted(wrong_hash_fixed)) or 'không có'}) xác nhận JPEG nguyên vẹn và cập nhật sha256; "
                f"sửa guideline theo jobs.csv ({', '.join(sorted(guideline_fixed)) or 'không có'}); "
                f"gom split thống nhất cho scene_leak ({', '.join(sorted(leaked_scenes)) or 'không có'}). "
                f"Ảnh rework giao đúng annotator/reviewer theo jobs.csv. "
                f"Ảnh chỉ lỗi panoptic giữ lại v2 và báo team panoptic: {', '.join(sorted(panoptic_notes)) or 'không có'}."
            ),
        ]
    ) + "\n"
    (v2_dir / "README.txt").write_text(readme_text, encoding="utf-8")
    return v2_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Build clean v2 handover package from v1 + errors.json.")
    parser.add_argument("--run", required=True, type=Path, help="run directory, e.g. runs/r34")
    args = parser.parse_args()
    v2_dir = build_handover(args.run)
    print(f"Đã dựng lô v2 tại {v2_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
