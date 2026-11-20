#!/usr/bin/env python3
"""Gộp các CSV review cá nhân thành một review_log.csv chuẩn, rồi (tuỳ chọn) gộp với lỗi luật thành errors.json.

Ví dụ (seed luyện tập):
  py -X utf8 validator/normalize_review.py --reviews submission/r34/review_assignments/by_member ^
      --candidates runs/r34/candidates.json --out runs/r34/review_log.csv ^
      --rules runs/r34/rules.json --errors runs/r34/errors.json

Đề ẩn: đổi đường dẫn sang submission/de_an/...

Quy tắc (nhóm đã chốt):
  - Mỗi file CSV cá nhân đặt tên dạng <số>_<Tên>.csv, ví dụ 04_Trinh.csv. Tên được thêm vào đầu note: "[Trinh] ...".
  - Gặp bất kỳ lỗi nào thì DỪNG, in danh sách lỗi và KHÔNG ghi file nào
    (tránh trường hợp verdict "confirm" bị merge_review.py bỏ qua mà không báo).

Kiểm tra:
  1. Header có đủ image,type,verdict,note.
  2. verdict chỉ là confirmed hoặc rejected (không tự sửa chữ khác, phải để người review sửa).
  3. type khớp với loại ứng viên trong candidates.json.
     Ứng viên class_disagreement: confirmed phải ghi class_swap hoặc category_swap (ảnh cho biết bên nào sai).
  4. Mỗi ứng viên (image, loại) có đúng một dòng: không thiếu, không thừa, không trùng.
  5. Note dài ít nhất 20 ký tự và không chép y hệt note của dòng khác.

Script chỉ đọc CSV review và candidates.json (không đọc _private/, data_source/ hay annotation COCO).
Bước gộp errors.json gọi nguyên bản scripts/merge_review.py, không sửa script của đề.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIELDS = ["image", "type", "verdict", "note"]
VERDICTS = {"confirmed", "rejected"}
MIN_NOTE = 20
# Loại ứng viên -> các type được phép ghi trong review_log
ALLOWED_TYPES = {
    "class_disagreement": {"class_disagreement", "class_swap", "category_swap"},
    "bbox_drift": {"bbox_drift"},
    "missing_box": {"missing_box"},
    "instance_merge": {"instance_merge"},
}
SWAP_TYPES = {"class_swap", "category_swap"}


def reviewer_name(path: Path) -> str:
    """04_Trinh.csv -> Trinh"""
    return re.sub(r"^\d+[_\-\s]*", "", path.stem) or path.stem


def candidate_key(image: str, typ: str) -> tuple[str, str]:
    """class_swap/category_swap đều là kết luận của ứng viên class_disagreement."""
    return image, "class_disagreement" if typ in SWAP_TYPES else typ


def load_candidates(path: Path) -> set[tuple[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(str(c["image"]).strip(), c["candidate_type"]) for c in data["candidates"]}


def load_reviews(folder: Path, problems: list[str]) -> list[dict]:
    files = sorted(folder.glob("*.csv"))
    if not files:
        problems.append(f"Không có file CSV nào trong {folder}")
    rows = []
    for f in files:
        with open(f, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            header = [h.strip() for h in (reader.fieldnames or [])]
            if not set(FIELDS) <= set(header):
                problems.append(f"{f.name}: header phải có {','.join(FIELDS)}, đang là {header}")
                continue
            for line_no, raw in enumerate(reader, start=2):
                row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
                if not any(row.values()):
                    continue  # bỏ dòng trống
                row["_who"] = reviewer_name(f)
                row["_where"] = f"{f.name}:{line_no}"
                rows.append(row)
    return rows


def check(rows: list[dict], candidates: set[tuple[str, str]], problems: list[str]) -> None:
    seen: Counter = Counter()
    for r in rows:
        where, typ, verdict = r["_where"], r["type"], r["verdict"]
        if verdict not in VERDICTS:
            problems.append(f"{where}: verdict '{verdict}' phải là confirmed hoặc rejected")
        key = candidate_key(r["image"], typ)
        if key[1] not in ALLOWED_TYPES:
            problems.append(f"{where}: type '{typ}' không phải loại ứng viên hợp lệ")
        elif typ not in ALLOWED_TYPES[key[1]]:
            problems.append(f"{where}: type '{typ}' không khớp ứng viên {key[1]}")
        if verdict == "confirmed" and typ == "class_disagreement":
            problems.append(f"{where}: confirmed bất đồng lớp phải ghi class_swap (detection sai) hoặc category_swap (panoptic sai)")
        if key not in candidates:
            problems.append(f"{where}: {key} không có trong candidates.json")
        if len(r["note"]) < MIN_NOTE:
            problems.append(f"{where}: note ngắn hơn {MIN_NOTE} ký tự, phải nói rõ thấy gì")
        seen[key] += 1
    for key, n in seen.items():
        if n > 1:
            problems.append(f"{key} bị review {n} lần (trùng dòng)")
    for key in sorted(candidates - set(seen)):
        problems.append(f"{key} chưa có ai review")
    notes = Counter(r["note"] for r in rows)
    for note, n in notes.items():
        if n > 1:
            problems.append(f"note bị chép giống nhau ở {n} dòng: '{note[:60]}...'")


def with_name(note: str, who: str) -> str:
    tag = f"[{who}]"
    return note if note.startswith(tag) else f"{tag} {note}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Gộp và chuẩn hoá CSV review cá nhân thành review_log.csv")
    ap.add_argument("--reviews", required=True, help="thư mục chứa các CSV cá nhân (<số>_<Tên>.csv)")
    ap.add_argument("--candidates", required=True, help="candidates.json do validator sinh ra")
    ap.add_argument("--out", required=True, help="review_log.csv đầu ra")
    ap.add_argument("--rules", help="rules.json (lỗi luật); có thì gộp tiếp ra errors.json")
    ap.add_argument("--errors", help="errors.json đầu ra (cần --rules)")
    args = ap.parse_args()
    if bool(args.rules) != bool(args.errors):
        ap.error("--rules và --errors phải đi cùng nhau")

    problems: list[str] = []
    candidates = load_candidates(Path(args.candidates))
    rows = load_reviews(Path(args.reviews), problems)
    check(rows, candidates, problems)
    if problems:
        print(f"DỪNG: {len(problems)} lỗi, chưa ghi file nào. Nhờ người review sửa rồi chạy lại:")
        for p in problems:
            print("  -", p)
        return 1

    rows.sort(key=lambda r: (r["image"], r["type"]))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        for r in rows:
            w.writerow([r["image"], r["type"], r["verdict"], with_name(r["note"], r["_who"])])

    verdicts = Counter(r["verdict"] for r in rows)
    confirmed = Counter(r["type"] for r in rows if r["verdict"] == "confirmed")
    who = Counter(r["_who"] for r in rows)
    print(f"OK: {len(rows)} dòng / {len(candidates)} ứng viên -> {out}")
    print(f"  confirmed {verdicts['confirmed']}, rejected {verdicts['rejected']}")
    print(f"  confirmed theo loại: {dict(sorted(confirmed.items()))}")
    print(f"  số dòng theo người: {dict(who)}")

    if args.rules:
        sys.stdout.flush()
        cmd = [sys.executable, str(REPO / "scripts" / "merge_review.py"),
               "--rules", args.rules, "--review", str(out), "--out", args.errors]
        return subprocess.call(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
