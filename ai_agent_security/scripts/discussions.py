#!/usr/bin/env python3
"""Fetch Kaggle competition discussion topics and save them locally."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import bleach
from kaggle import KaggleApi
from slugify import slugify

ROOT = Path(__file__).resolve().parents[1]
DISCUSSIONS_DIR = ROOT / "discussions" / "topics"
INDEX_PATH = ROOT / "discussions" / "index.csv"
COMPETITION = "ai-agent-security-multi-step-tool-attacks"
COMPETITION_URL = f"https://www.kaggle.com/competitions/{COMPETITION}/discussion"

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
    "notes",
]


def _clean_html(text: str) -> str:
    if not text:
        return ""
    return bleach.clean(text, tags=[], strip=True).strip()


def _topic_url(topic_id: int) -> str:
    return f"{COMPETITION_URL}/{topic_id}"


def _topic_filename(topic_id: int, title: str) -> str:
    slug = slugify(title)[:80] or "topic"
    return f"{topic_id}-{slug}.md"


def _parse_topic_ref(value: str) -> int:
    value = value.strip()
    if value.isdigit():
        return int(value)
    match = re.search(r"/discussion/(\d+)", value)
    if match:
        return int(match.group(1))
    raise ValueError(f"Could not parse topic id from: {value!r}")


def _parse_topic_refs(values: list[str]) -> list[int]:
    return [_parse_topic_ref(value) for value in values]


def _read_index() -> list[dict[str, str]]:
    if not INDEX_PATH.exists():
        return []
    with INDEX_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_index(rows: list[dict[str, str]]) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _upsert_index(row: dict[str, str]) -> None:
    rows = _read_index()
    topic_id = row["topic_id"]
    updated = False
    for i, existing in enumerate(rows):
        if existing["topic_id"] == topic_id:
            merged = {**existing, **row}
            rows[i] = merged
            updated = True
            break
    if not updated:
        rows.append(row)
    _write_index(rows)


def _get_api() -> KaggleApi:
    api = KaggleApi()
    api.authenticate()
    return api


def _list_topics(api: KaggleApi, sort_by: str, max_pages: int) -> list:
    topics = []
    for page in range(1, max_pages + 1):
        response = api.competition_list_topics(
            competition=COMPETITION,
            sort_by=sort_by,
            page=page,
        )
        batch = response.topics or []
        if not batch:
            break
        topics.extend(batch)
    return topics


def _render_comment(comment, depth: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = "  " * depth
    author = getattr(comment, "author_name", "Unknown")
    date = getattr(comment, "post_date", "")
    votes = getattr(comment, "votes", 0)
    comment_id = getattr(comment, "id", "")
    content = _clean_html(getattr(comment, "content", ""))
    if comment_id:
        lines.append(f'{prefix}<a id="{comment_id}"></a>')
    lines.append(f"{prefix}- **{author}** ({date}, votes: {votes}, id: {comment_id})")
    if content:
        for line in content.splitlines():
            lines.append(f"{prefix}  {line}")
    lines.append("")
    for reply in getattr(comment, "replies", None) or []:
        lines.extend(_render_comment(reply, depth + 1))
    return lines


def _save_topic(api: KaggleApi, topic_id: int, notes: str = "") -> Path:
    topic, comments, _ = api.forums_topic_show(topic_id)
    if topic is None:
        raise ValueError(f"Topic not found: {topic_id}")

    title = getattr(topic, "title", f"topic-{topic_id}")
    filename = _topic_filename(topic_id, title)
    out_path = DISCUSSIONS_DIR / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)

    body_lines = [
        f"# {title}",
        "",
        f"- Topic ID: {topic_id}",
        f"- URL: {_topic_url(topic_id)}",
        f"- Author: {getattr(topic, 'author_name', '')}",
        f"- Posted: {getattr(topic, 'post_date', '')}",
        f"- Votes: {getattr(topic, 'votes', 0)}",
        f"- Comments: {getattr(topic, 'comment_count', 0)}",
        f"- Fetched: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
    ]
    if notes:
        body_lines.extend([f"> Notes: {notes}", ""])

    topic_content = _clean_html(getattr(topic, "content", ""))
    body_lines.extend(["## Post", "", topic_content or "(empty)", ""])

    if comments:
        body_lines.extend(["## Comments", ""])
        for comment in comments:
            body_lines.extend(_render_comment(comment))

    out_path.write_text("\n".join(body_lines).rstrip() + "\n", encoding="utf-8")

    rel_path = str(out_path.relative_to(ROOT))
    _upsert_index(
        {
            "topic_id": str(topic_id),
            "title": title,
            "author": str(getattr(topic, "author_name", "")),
            "votes": str(getattr(topic, "votes", 0)),
            "comment_count": str(getattr(topic, "comment_count", 0)),
            "post_date": str(getattr(topic, "post_date", "")),
            "url": _topic_url(topic_id),
            "saved_path": rel_path,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "notes": notes,
        }
    )
    return out_path


def cmd_list(args: argparse.Namespace) -> int:
    api = _get_api()
    topics = _list_topics(api, sort_by=args.sort_by, max_pages=args.pages)
    if not topics:
        print("No topics found.")
        return 0

    saved_ids = {row["topic_id"] for row in _read_index()}
    print(f"{'id':>8}  {'votes':>5}  {'cmts':>4}  saved  title")
    print("-" * 80)
    for topic in topics[: args.limit]:
        topic_id = str(getattr(topic, "id", ""))
        marker = "yes" if topic_id in saved_ids else "-"
        print(
            f"{topic_id:>8}  {getattr(topic, 'votes', 0):>5}  "
            f"{getattr(topic, 'comment_count', 0):>4}  {marker:<5}  "
            f"{getattr(topic, 'title', '')}"
        )
    print(f"\nTotal listed: {min(len(topics), args.limit)} / {len(topics)}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    api = _get_api()
    topic_ids: list[int] = []

    if args.topic_refs:
        topic_ids = _parse_topic_refs(args.topic_refs)
    elif args.top:
        topics = _list_topics(api, sort_by=args.sort_by, max_pages=args.pages)
        topic_ids = [int(getattr(t, "id")) for t in topics[: args.top]]
    else:
        print("Specify topic ID/URL or --top N.", file=sys.stderr)
        return 1

    for topic_id in topic_ids:
        path = _save_topic(api, topic_id, notes=args.notes or "")
        print(f"Saved topic {topic_id} -> {path.relative_to(ROOT)}")
    print(f"Index updated: {INDEX_PATH.relative_to(ROOT)}")
    return 0


def cmd_show_index(_: argparse.Namespace) -> int:
    rows = _read_index()
    if not rows:
        print("No saved discussions yet.")
        print("Run: uv run python scripts/discussions.py fetch --top 10")
        return 0

    print(f"{'topic_id':>8}  {'votes':>5}  saved_path")
    print("-" * 80)
    for row in rows:
        print(f"{row['topic_id']:>8}  {row['votes']:>5}  {row['saved_path']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch Kaggle competition discussions into this repo.")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List discussion topics on Kaggle.")
    list_parser.add_argument(
        "--sort-by",
        default="top",
        choices=["hot", "top", "new", "recent", "active", "relevance"],
        help="Sort order (default: top).",
    )
    list_parser.add_argument("--pages", type=int, default=3, help="Pages to fetch (20 topics/page).")
    list_parser.add_argument("--limit", type=int, default=30, help="Max rows to print.")
    list_parser.set_defaults(func=cmd_list)

    fetch_parser = sub.add_parser("fetch", help="Download topic(s) with comments as Markdown.")
    fetch_parser.add_argument(
        "topic_refs",
        nargs="*",
        help="Topic ID or Kaggle discussion URL (e.g. .../discussion/710234).",
    )
    fetch_parser.add_argument("--top", type=int, help="Fetch top N topics by sort order.")
    fetch_parser.add_argument(
        "--sort-by",
        default="top",
        choices=["hot", "top", "new", "recent", "active", "relevance"],
    )
    fetch_parser.add_argument("--pages", type=int, default=3)
    fetch_parser.add_argument("--notes", default="", help="Optional note stored in index.csv.")
    fetch_parser.set_defaults(func=cmd_fetch)

    index_parser = sub.add_parser("index", help="Show locally saved discussion index.")
    index_parser.set_defaults(func=cmd_show_index)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
