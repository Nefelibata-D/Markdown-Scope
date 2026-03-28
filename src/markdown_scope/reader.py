from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .exceptions import InvalidRangeError, MDScopeError, SectionNotFoundError
from .index_models import PublicIndex, PublicSection, RootIndex


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


def read_section(
    index: PublicIndex | RootIndex,
    root: Path,
    section_id: str,
    max_lines: int,
) -> dict:
    section, file_name = _find_section(index, section_id)
    if not section:
        raise SectionNotFoundError(f"Section id not found: {section_id}")
    file_path = root / file_name
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise MDScopeError(f"Encoding error when reading markdown file: {file_path}") from exc

    start = section.start
    end = section.end
    effective_end = end
    if start > 0 and (end - start + 1) > max_lines:
        effective_end = start + max_lines - 1
    content = "\n".join(lines[start - 1 : effective_end]) if start > 0 else "\n".join(lines[:effective_end])
    returned_start = start
    returned_end = effective_end
    truncated = effective_end < end

    return {
        "id": section.id,
        "title": section.title,
        "file_name": file_name,
        "requested_start": section.start,
        "requested_end": section.end,
        "returned_start": returned_start,
        "returned_end": returned_end,
        "truncated": truncated,
        "content": content,
    }


@dataclass
class _NodeRef:
    node: PublicSection
    file_name: str
    parent: "_NodeRef | None" = None
    children: list["_NodeRef"] | None = None

    def __post_init__(self):
        if self.children is None:
            self.children = []


def read_sections_contextual(
    index: PublicIndex | RootIndex,
    root: Path,
    section_ids: list[str],
    max_lines: int,
) -> dict:
    if not section_ids:
        raise SectionNotFoundError("No section ids provided.")

    all_files, id_map = _build_ref_index(index)
    missing = [sec_id for sec_id in section_ids if sec_id not in id_map]
    if missing:
        raise SectionNotFoundError(f"Section id not found: {', '.join(missing)}")

    requested_refs = [id_map[sec_id] for sec_id in section_ids]
    per_file: dict[str, list[_NodeRef]] = {}
    for ref in requested_refs:
        per_file.setdefault(ref.file_name, []).append(ref)

    file_results: list[dict] = []
    for file_name in [f for f in all_files if f in per_file]:
        file_path = root / file_name
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise MDScopeError(f"Encoding error when reading markdown file: {file_path}") from exc

        targets = _prune_redundant_targets(per_file[file_name])
        include_map: dict[str, str] = {}
        for target in targets:
            for ancestor in _ancestors(target):
                include_map[ancestor.node.id] = "context"
            for desc in _descendants(target):
                include_map[desc.node.id] = "target"

        roots = _top_roots_for_file(index, file_name)
        root_refs = _roots_to_refs(roots, file_name)
        chunks: list[tuple[int, int]] = []
        for root_ref in root_refs:
            _collect_contextual_chunks(root_ref, include_map, chunks)

        total_count = _count_rendered_lines(lines, chunks)
        content, returned_end, returned_count = _render_chunks(lines, chunks, max_lines)
        requested_start = min(t.node.start for t in targets)
        requested_end = max(t.node.end for t in targets)
        returned_start = chunks[0][0] if chunks else requested_start
        truncated = returned_count < total_count

        file_results.append(
            {
                "file_name": file_name,
                "requested_ids": [t.node.id for t in targets],
                "requested_start": requested_start,
                "requested_end": requested_end,
                "returned_start": returned_start,
                "returned_end": returned_end,
                "truncated": truncated,
                "content": content,
            }
        )

    if len(file_results) == 1:
        payload = dict(file_results[0])
        payload["requested_ids"] = section_ids
        return payload
    return {"requested_ids": section_ids, "files": file_results}


def _find_section(index: PublicIndex | RootIndex, section_id: str) -> tuple[PublicSection | None, str]:
    for file in index.files:
        found = _find_in_nodes(file.sections, section_id)
        if found:
            return found, _file_path_from_index_file(file)
    return None, ""


def _file_path_from_index_file(file) -> str:
    if hasattr(file, "file_name"):
        return file.file_name
    if hasattr(file, "path"):
        return file.path
    if hasattr(file, "file-name"):
        return getattr(file, "file-name")
    raise MDScopeError("Index file entry is missing file path field.")


def _find_in_nodes(nodes: list[PublicSection], section_id: str) -> PublicSection | None:
    for node in nodes:
        if node.id == section_id:
            return node
        found = _find_in_nodes(node.children, section_id)
        if found:
            return found
    return None


def _build_ref_index(index: PublicIndex | RootIndex) -> tuple[list[str], dict[str, _NodeRef]]:
    files: list[str] = []
    id_map: dict[str, _NodeRef] = {}
    for file in index.files:
        file_name = _file_path_from_index_file(file)
        files.append(file_name)
        roots = _roots_to_refs(file.sections, file_name)
        stack = list(roots)
        while stack:
            ref = stack.pop()
            id_map[ref.node.id] = ref
            stack.extend(ref.children)
    return files, id_map


def _roots_to_refs(nodes: list[PublicSection], file_name: str, parent: _NodeRef | None = None) -> list[_NodeRef]:
    refs: list[_NodeRef] = []
    for node in nodes:
        ref = _NodeRef(node=node, file_name=file_name, parent=parent)
        ref.children = _roots_to_refs(node.children, file_name, ref)
        refs.append(ref)
    return refs


def _top_roots_for_file(index: PublicIndex | RootIndex, file_name: str) -> list[PublicSection]:
    for file in index.files:
        if _file_path_from_index_file(file) == file_name:
            return file.sections
    return []


def _prune_redundant_targets(targets: list[_NodeRef]) -> list[_NodeRef]:
    target_ids = {t.node.id for t in targets}
    pruned: list[_NodeRef] = []
    for target in sorted(targets, key=lambda t: (t.node.start, t.node.end)):
        parent = target.parent
        redundant = False
        while parent is not None:
            if parent.node.id in target_ids:
                redundant = True
                break
            parent = parent.parent
        if not redundant:
            pruned.append(target)
    return pruned


def _ancestors(ref: _NodeRef) -> list[_NodeRef]:
    items: list[_NodeRef] = []
    current = ref.parent
    while current is not None:
        items.append(current)
        current = current.parent
    return list(reversed(items))


def _descendants(ref: _NodeRef) -> list[_NodeRef]:
    items: list[_NodeRef] = [ref]
    for child in ref.children:
        items.extend(_descendants(child))
    return items


def _context_range(ref: _NodeRef) -> tuple[int, int]:
    if not ref.children:
        return ref.node.start, ref.node.end
    first_child_start = min(c.node.start for c in ref.children)
    end = first_child_start - 1
    if end < ref.node.start:
        end = ref.node.start
    return ref.node.start, end


def _collect_contextual_chunks(ref: _NodeRef, include_map: dict[str, str], chunks: list[tuple[int, int]]) -> None:
    mode = include_map.get(ref.node.id)
    if mode is None:
        return
    if mode == "target":
        chunks.append((ref.node.start, ref.node.end))
        return
    start, end = _context_range(ref)
    chunks.append((start, end))
    for child in ref.children:
        _collect_contextual_chunks(child, include_map, chunks)


def _render_chunks(lines: list[str], chunks: list[tuple[int, int]], max_lines: int) -> tuple[str, int, int]:
    emitted: list[tuple[int | None, str]] = []
    for idx, (start, end) in enumerate(chunks):
        safe_start = max(1, start)
        safe_end = min(end, len(lines))
        if safe_start <= safe_end:
            for line_no in range(safe_start, safe_end + 1):
                emitted.append((line_no, lines[line_no - 1]))
        if idx < len(chunks) - 1:
            emitted.append((None, ""))

    truncated_emitted = emitted[:max_lines]
    text = "\n".join(line for _, line in truncated_emitted)
    source_lines = [line_no for line_no, _ in truncated_emitted if line_no is not None]
    returned_end = max(source_lines) if source_lines else 0
    return text, returned_end, len(truncated_emitted)


def _count_rendered_lines(lines: list[str], chunks: list[tuple[int, int]]) -> int:
    total = 0
    for idx, (start, end) in enumerate(chunks):
        safe_start = max(1, start)
        safe_end = min(end, len(lines))
        if safe_start <= safe_end:
            total += safe_end - safe_start + 1
        if idx < len(chunks) - 1:
            total += 1
    return total
