from __future__ import annotations

from pathlib import Path

from .exceptions import InvalidRangeError, MDScopeError, SectionNotFoundError
from .index_models import PublicIndex, PublicSection


def read_lines(file_path: Path, start: int, end: int, max_lines: int) -> dict:
    if start <= 0 or end <= 0:
        raise InvalidRangeError("start/end must be 1-based positive integers.")
    if start > end:
        raise InvalidRangeError("start cannot be greater than end.")
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise MDScopeError(f"Encoding error when reading markdown file: {file_path}") from exc

    if start > len(lines):
        raise InvalidRangeError(f"start {start} exceeds file line count {len(lines)}.")

    requested_count = end - start + 1
    effective_end = min(end, len(lines))
    if requested_count > max_lines:
        effective_end = start + max_lines - 1

    content = "\n".join(lines[start - 1 : effective_end])
    return {
        "file_path": str(file_path),
        "requested_start": start,
        "requested_end": end,
        "returned_start": start,
        "returned_end": effective_end,
        "truncated": effective_end < end,
        "content": content,
    }


def read_section(index: PublicIndex, root: Path, section_id: str, max_lines: int) -> dict:
    section, file_name = _find_section(index, section_id)
    if not section:
        raise SectionNotFoundError(f"Section id not found: {section_id}")
    file_path = root / file_name
    lines = file_path.read_text(encoding="utf-8").splitlines()
    start = section.start
    end = section.end
    effective_end = end
    if start > 0 and (end - start + 1) > max_lines:
        effective_end = start + max_lines - 1
    content = "\n".join(lines[start - 1 : effective_end]) if start > 0 else "\n".join(lines[:effective_end])
    return {
        "id": section.id,
        "title": section.title,
        "file_name": file_name,
        "requested_start": start,
        "requested_end": end,
        "returned_start": start,
        "returned_end": effective_end,
        "truncated": effective_end < end,
        "content": content,
    }


def _find_section(index: PublicIndex, section_id: str) -> tuple[PublicSection | None, str]:
    for file in index.files:
        for section in _iter_sections(file.sections):
            if section.id == section_id:
                return section, file.file_name
    return None, ""


def _iter_sections(nodes: list[PublicSection]):
    for node in nodes:
        yield node
        yield from _iter_sections(node.children)
