#!/usr/bin/env python3
"""Fetch Kaggriculture discussion topics through the official Kaggle API."""

from __future__ import annotations

import argparse
import csv
import html
import re
from datetime import datetime, timezone
from pathlib import Path

import bleach
from kaggle import KaggleApi
from slugify import slugify


ROOT = Path(__file__).resolve().parents[1]
COMPETITION = "kaggriculture"
BASE_URL = f"https://www.kaggle.com/competitions/{COMPETITION}/discussion"
TOPICS_DIR = ROOT / "discussions" / "topics"
INDEX_PATH = ROOT / "discussions" / "index.csv"
INDEX_FIELDS = [
    "topic_id",
    "title",
    "author",
    "votes",
    "comment_count",
    "post_date",
    "url",
    "saved_path",
    "fetched_at",
]


def clean_html(value: str) -> str:
    return html.unescape(bleach.clean(value or "", tags=[], strip=True)).strip()


def topic_id(value: str) -> int:
    if value.isdigit():
        return int(value)
    match = re.search(r"/discussion/(\d+)", value)
    if not match:
        raise ValueError(f"Invalid topic ID or URL: {value}")
    return int(match.group(1))


def render_comment(comment, depth: int = 0) -> list[str]:
    indent = "  " * depth
    content = clean_html(getattr(comment, "content", ""))
    lines = [
        f"{indent}- **{getattr(comment, 'author_name', 'Unknown')}** "
        f"({getattr(comment, 'post_date', '')}, votes: {getattr(comment, 'votes', 0)})"
    ]
    lines.extend(f"{indent}  {line}" for line in content.splitlines())
    lines.append("")
    for reply in getattr(comment, "replies", None) or []:
        lines.extend(render_comment(reply, depth + 1))
    return lines


def read_index() -> list[dict[str, str]]:
    if not INDEX_PATH.exists():
        return []
    with INDEX_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_index(rows: list[dict[str, str]]) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: int(row["topic_id"])))


def save_topic(api: KaggleApi, ref: str) -> Path:
    identifier = topic_id(ref)
    topic, comments, _ = api.forums_topic_show(identifier)
    if topic is None:
        raise ValueError(f"Topic not found: {identifier}")

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    title = getattr(topic, "title", f"topic-{identifier}")
    path = TOPICS_DIR / f"{identifier}-{slugify(title)[:80] or 'topic'}.md"
    lines = [
        f"# {title}",
        "",
        f"- Topic ID: {identifier}",
        f"- URL: {BASE_URL}/{identifier}",
        f"- Author: {getattr(topic, 'author_name', '')}",
        f"- Posted: {getattr(topic, 'post_date', '')}",
        f"- Votes: {getattr(topic, 'votes', 0)}",
        f"- Comments: {getattr(topic, 'comment_count', 0)}",
        f"- Fetched: {fetched_at}",
        "",
        "## Post",
        "",
        clean_html(getattr(topic, "content", "")) or "(empty)",
        "",
    ]
    if comments:
        lines.extend(["## Comments", ""])
        for comment in comments:
            lines.extend(render_comment(comment))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    rows = read_index()
    row = {
        "topic_id": str(identifier),
        "title": title,
        "author": str(getattr(topic, "author_name", "")),
        "votes": str(getattr(topic, "votes", 0)),
        "comment_count": str(getattr(topic, "comment_count", 0)),
        "post_date": str(getattr(topic, "post_date", "")),
        "url": f"{BASE_URL}/{identifier}",
        "saved_path": str(path.relative_to(ROOT)),
        "fetched_at": fetched_at,
    }
    rows = [existing for existing in rows if existing["topic_id"] != str(identifier)]
    rows.append(row)
    write_index(rows)
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("topics", nargs="+", help="Topic IDs or discussion URLs")
    args = parser.parse_args()
    api = KaggleApi()
    api.authenticate()
    for ref in args.topics:
        path = save_topic(api, ref)
        print(f"Saved {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
