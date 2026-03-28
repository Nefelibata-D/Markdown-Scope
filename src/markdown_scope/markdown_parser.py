from __future__ import annotations

import re
from dataclasses import dataclass, field


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")


@dataclass
class ParsedSection:
    title: str
    level: int
    start: int
    end: int
    heading_path: list[str] = field(default_factory=list)
    occurrence: int = 1
    children: list["ParsedSection"] = field(default_factory=list)


def parse_markdown_sections_with_level(
    lines: list[str],
    file_title: str,
    *,
    top_level_from: int = 1,
) -> list[ParsedSection]:
    if top_level_from < 1 or top_level_from > 6:
        raise ValueError("top_level_from must be within 1..6")

    line_count = len(lines)
    raw_headings: list[tuple[str, int, int]] = []  # title, level, start
    in_fenced_block = False
    fence_char = ""
    fence_len = 0
    in_front_matter = False
    in_html_comment = False

    for line_no, line in enumerate(lines, start=1):
        raw = line.rstrip("\n")
        stripped = raw.strip()

        if line_no == 1 and stripped == "---":
            in_front_matter = True
            continue
        if in_front_matter:
            if stripped in {"---", "..."}:
                in_front_matter = False
            continue

        if not in_html_comment and stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_html_comment = True
            continue
        if in_html_comment:
            if "-->" in raw:
                in_html_comment = False
            continue

        fence_match = FENCE_RE.match(raw)
        if fence_match:
            marker = fence_match.group(1)
            marker_char = marker[0]
            marker_len = len(marker)
            if not in_fenced_block:
                in_fenced_block = True
                fence_char = marker_char
                fence_len = marker_len
            else:
                if marker_char == fence_char and marker_len >= fence_len:
                    in_fenced_block = False
                    fence_char = ""
                    fence_len = 0
            continue

        if in_fenced_block:
            continue

        match = HEADING_RE.match(raw)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip() or f"Untitled-{line_no}"
        raw_headings.append((title, level, line_no))

    if not raw_headings:
        return [
            ParsedSection(
                title=f"Document: {file_title}",
                level=1,
                start=1 if line_count > 0 else 0,
                end=line_count,
                heading_path=[f"Document: {file_title}"],
                occurrence=1,
            )
        ]

    keep_indices = [idx for idx, (_, level, _) in enumerate(raw_headings) if level >= top_level_from]
    if not keep_indices:
        return [
            ParsedSection(
                title=f"Document: {file_title}",
                level=1,
                start=1 if line_count > 0 else 0,
                end=line_count,
                heading_path=[f"Document: {file_title}"],
                occurrence=1,
            )
        ]

    headings: list[ParsedSection] = []
    prev_kept_idx = -1
    for idx in keep_indices:
        title, level, start = raw_headings[idx]
        segment = raw_headings[prev_kept_idx + 1 : idx]
        shallow_starts = [seg_start for _, seg_level, seg_start in segment if seg_level < top_level_from]
        if shallow_starts:
            effective_start = shallow_starts[-1]
        elif prev_kept_idx == -1 and start > 1:
            effective_start = 1
        else:
            effective_start = start
        normalized_level = level - top_level_from + 1
        headings.append(
            ParsedSection(
                title=title,
                level=normalized_level,
                start=effective_start,
                end=line_count,
            )
        )
        prev_kept_idx = idx

    if not headings:
        return [
            ParsedSection(
                title=f"Document: {file_title}",
                level=1,
                start=1 if line_count > 0 else 0,
                end=line_count,
                heading_path=[f"Document: {file_title}"],
                occurrence=1,
            )
        ]

    for idx, current in enumerate(headings):
        next_end = line_count
        for nxt in headings[idx + 1 :]:
            if nxt.level <= current.level:
                next_end = nxt.start - 1
                break
        current.end = next_end

    roots: list[ParsedSection] = []
    stack: list[ParsedSection] = []
    for section in headings:
        while stack and stack[-1].level >= section.level:
            stack.pop()
        if stack:
            stack[-1].children.append(section)
        else:
            roots.append(section)
        stack.append(section)

    _attach_heading_paths_and_occurrence(roots)
    return roots


def _attach_heading_paths_and_occurrence(nodes: list[ParsedSection], parent_path: list[str] | None = None) -> None:
    parent_path = parent_path or []
    counter: dict[tuple[str, ...], int] = {}
    for node in nodes:
        node.heading_path = [*parent_path, node.title]
        key = tuple(node.heading_path)
        counter[key] = counter.get(key, 0) + 1
        node.occurrence = counter[key]
        if node.children:
            _attach_heading_paths_and_occurrence(node.children, node.heading_path)


def parse_markdown_sections(lines: list[str], file_title: str) -> list[ParsedSection]:
    return parse_markdown_sections_with_level(lines, file_title, top_level_from=1)
