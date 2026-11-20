#!/usr/bin/env python3
"""Split cross-check candidates into balanced per-member image-review queues.

All candidate types for the same image are assigned to the same reviewer.
The script writes a master assignment CSV plus one review CSV and HTML gallery
per member. It reads only candidates.json and never opens private truth files.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


def safe_slug(name: str, index: int) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_name).strip("_").lower()
    if not slug:
        raise ValueError(f"member name has no usable filename characters: {name!r}")
    return f"{index:02d}_{slug}"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_member_html(name: str, rows: list[dict[str, str]]) -> str:
    body_rows = []
    for row in rows:
        image = html.escape(row["image"], quote=True)
        kind = html.escape(row["type"])
        src = f"../../review_previews/{image}.jpg"
        body_rows.append(
            "<tr>"
            f"<td>{image}</td><td>{kind}</td>"
            f"<td><a href=\"{src}\">Open overlay</a>"
            f"<br><img loading=\"lazy\" width=\"480\" src=\"{src}\" alt=\"{image}\"></td>"
            "</tr>"
        )
    safe_name = html.escape(name)
    return (
        "<!doctype html>\n<html lang=\"vi\"><head><meta charset=\"utf-8\">"
        f"<title>Review queue — {safe_name}</title>"
        "<style>body{font:14px sans-serif;margin:24px}"
        "table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:8px;vertical-align:top}"
        "th{position:sticky;top:0;background:#fff}</style></head><body>"
        f"<h1>Review queue — {safe_name}</h1>"
        f"<p>{len({r['image'] for r in rows})} unique images; one CSV row per candidate type.</p>"
        "<table><thead><tr><th>Image</th><th>Candidate</th><th>Overlay</th></tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table></body></html>\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path, help="candidates.json from validator")
    parser.add_argument("--out", required=True, type=Path, help="new output folder for assignment files")
    parser.add_argument("--members", required=True, nargs="+", help="reviewer names in assignment order")
    args = parser.parse_args()

    if len(args.members) < 2:
        parser.error("provide at least two reviewer names")
    if len({name.casefold() for name in args.members}) != len(args.members):
        parser.error("reviewer names must be unique")
    if not args.candidates.is_file():
        parser.error(f"candidates file not found: {args.candidates}")
    if args.out.exists() and any(args.out.iterdir()):
        parser.error(f"output folder is not empty; choose a new folder: {args.out}")

    try:
        data: dict[str, Any] = json.loads(args.candidates.read_text(encoding="utf-8"))
        raw_candidates = data["candidates"]
        by_image: dict[str, list[str]] = defaultdict(list)
        seen_pairs: set[tuple[str, str]] = set()
        for item in raw_candidates:
            image = str(item["image"]).strip()
            kind = str(item["candidate_type"]).strip()
            if not image or Path(image).name != image or image in {".", ".."}:
                raise ValueError(f"unsafe or empty image id: {image!r}")
            if not kind:
                raise ValueError(f"empty candidate type for image {image}")
            pair = (image, kind)
            if pair in seen_pairs:
                raise ValueError(f"duplicate candidate row: {pair}")
            seen_pairs.add(pair)
            by_image[image].append(kind)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"cannot read candidate rows: {exc}")

    if not by_image:
        parser.error("candidates.json contains no review rows")

    member_images: list[list[str]] = [[] for _ in args.members]
    assignment_by_image: dict[str, str] = {}
    for index, image in enumerate(sorted(by_image)):
        member_index = index % len(args.members)
        member_images[member_index].append(image)
        assignment_by_image[image] = args.members[member_index]

    output = args.out
    by_member = output / "by_member"
    by_member.mkdir(parents=True, exist_ok=True)
    master_rows: list[dict[str, str]] = []
    index_links = []

    for index, name in enumerate(args.members, start=1):
        slug = safe_slug(name, index)
        member_rows = [
            {"image": image, "type": kind, "verdict": "", "note": ""}
            for image in member_images[index - 1]
            for kind in sorted(by_image[image])
        ]
        write_csv(by_member / f"{slug}.csv", ["image", "type", "verdict", "note"], member_rows)
        (by_member / f"{slug}.html").write_text(
            build_member_html(name, member_rows), encoding="utf-8", newline="\n"
        )
        index_links.append(
            f"<li><a href=\"by_member/{slug}.html\">{html.escape(name)}</a> "
            f"({len(member_images[index - 1])} images)</li>"
        )

    for image in sorted(by_image):
        master_rows.append(
            {
                "image": image,
                "assigned_to": assignment_by_image[image],
                "candidate_types": ";".join(sorted(by_image[image])),
                "preview": f"../review_previews/{image}.jpg",
            }
        )
    write_csv(output / "assignments.csv", ["image", "assigned_to", "candidate_types", "preview"], master_rows)
    (output / "index.html").write_text(
        "<!doctype html><html lang=\"vi\"><meta charset=\"utf-8\"><title>Review assignments</title>"
        "<body><h1>Review assignments</h1><ul>"
        + "".join(index_links)
        + "</ul></body></html>\n",
        encoding="utf-8",
        newline="\n",
    )

    counts = ", ".join(
        f"{name}: {len(member_images[i])} images/{sum(len(by_image[x]) for x in member_images[i])} rows"
        for i, name in enumerate(args.members)
    )
    print(f"Assigned {len(by_image)} images and {len(seen_pairs)} candidate rows to {len(args.members)} reviewers")
    print(counts)
    print(f"Master: {output / 'assignments.csv'}; galleries: {by_member}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
