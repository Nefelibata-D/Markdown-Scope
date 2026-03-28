from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .exceptions import MDScopeError, SummaryProviderError
from .index_models import FileIndex, IndexStats, RootIndex, SectionNode
from .markdown_parser import ParsedSection, parse_markdown_sections
from .summary.providers import SummaryProvider
from .utils import relative_posix, section_id_from_title, sha256_text, slugify_title


@dataclass
class BuildOptions:
    root: Path
    include_patterns: list[str] | None = None
    fail_on_summary_error: bool = False
    progress_cb: Callable[[dict], None] | None = None
    summary_root_level: int = 2
    include_excluded_ancestors_as_context: bool = True


@dataclass
class SummaryGroup:
    key: str
    group_title: str
    context_ancestor_id: str | None
    target_ids: list[str]
    top_target_ids: list[str]


def collect_markdown_files(root: Path, include_patterns: list[str] | None = None) -> list[Path]:
    if not root.exists():
        raise MDScopeError(f"Root path does not exist: {root}")
    candidates: list[Path] = []
    if include_patterns:
        for pattern in include_patterns:
            candidates.extend(root.rglob(pattern))
    else:
        candidates.extend(root.rglob("*.md"))
    files = sorted({p for p in candidates if p.is_file()})
    return files


def build_index(
    options: BuildOptions,
    summary_provider: SummaryProvider,
    *,
    existing_reuse_lookup: dict[tuple[str, tuple[str, ...], str], tuple[str, str | None]] | None = None,
) -> RootIndex:
    files = collect_markdown_files(options.root, options.include_patterns)
    if not files:
        return RootIndex(root_path=str(options.root.resolve()), provider=summary_provider.name, files=[], stats=IndexStats())

    built_files: list[FileIndex] = []
    stats = IndexStats(file_count=len(files), section_count=0, summary_failures=0)
    reuse_lookup = existing_reuse_lookup or {}

    for file_path in files:
        current_index = len(built_files) + 1
        rel_path = relative_posix(options.root, file_path)
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise MDScopeError(f"Encoding error when reading markdown file: {file_path}") from exc
        lines = text.splitlines()
        parsed_roots = parse_markdown_sections(lines, file_path.name)
        if options.progress_cb:
            options.progress_cb(
                {
                    "type": "file_start",
                    "file_index": current_index,
                    "file_total": len(files),
                    "file_path": rel_path,
                    "line_count": len(lines),
                    "top_level_count": len(parsed_roots),
                    "section_count": _count_parsed_sections(parsed_roots),
                }
            )
        slug_counts = _collect_slug_counts(parsed_roots)
        file_sha = sha256_text(text)
        section_nodes = _convert_sections(
            parsed_roots,
            lines,
            rel_path,
            summary_provider,
            reuse_lookup,
            stats,
            set(),
            slug_counts,
            options.progress_cb,
            summary_root_level=options.summary_root_level,
            include_excluded_ancestors_as_context=options.include_excluded_ancestors_as_context,
            fail_on_summary_error=options.fail_on_summary_error,
        )
        stats.section_count += _count_sections(section_nodes)
        built_files.append(
            FileIndex(
                path=rel_path,
                sha256=file_sha,
                line_count=len(lines),
                summary_root_level=options.summary_root_level,
                include_excluded_ancestors_as_context=options.include_excluded_ancestors_as_context,
                sections=section_nodes,
            )
        )
        if options.progress_cb:
            options.progress_cb(
                {
                    "type": "file_done",
                    "file_index": current_index,
                    "file_total": len(files),
                    "file_path": rel_path,
                }
            )

    return RootIndex(
        root_path=str(options.root.resolve()),
        provider=summary_provider.name,
        files=built_files,
        stats=stats,
    )


def build_reuse_lookup(index: RootIndex) -> dict[tuple[str, tuple[str, ...], str], tuple[str, str | None]]:
    lookup: dict[tuple[str, tuple[str, ...], str], tuple[str, str | None]] = {}
    for file in index.files:
        for section in _iter_sections(file.sections):
            key = (section.file_path, tuple(section.heading_path), section.content_hash)
            lookup[key] = (section.id, section.summary)
    return lookup


def _convert_sections(
    sections: list[ParsedSection],
    lines: list[str],
    rel_path: str,
    summary_provider: SummaryProvider,
    reuse_lookup: dict[tuple[str, tuple[str, ...], str], tuple[str, str | None]],
    stats: IndexStats,
    used_ids: set[str],
    slug_counts: dict[str, int],
    progress_cb: Callable[[dict], None] | None,
    *,
    summary_root_level: int,
    include_excluded_ancestors_as_context: bool,
    fail_on_summary_error: bool,
) -> list[SectionNode]:
    converted: list[SectionNode] = []
    pending_map: dict[str, tuple[str, str]] = {}
    for section in sections:
        node, pending = _build_section_tree(
            section,
            lines,
            rel_path,
            reuse_lookup,
            used_ids,
            slug_counts,
        )
        converted.append(node)
        pending_map.update(pending)

    groups = _build_summary_groups(
        converted,
        summary_root_level=summary_root_level,
        include_excluded_ancestors_as_context=include_excluded_ancestors_as_context,
    )
    node_lookup = _build_node_lookup(converted)
    target_ids = {target_id for group in groups for target_id in group.target_ids}
    _mark_summary_status(converted, target_ids)

    for top_index, group in enumerate(groups, start=1):
        ids_to_summarize = [target_id for target_id in group.target_ids if target_id in pending_map]
        if not ids_to_summarize:
            continue
        if progress_cb:
            progress_cb(
                {
                    "type": "top_section_start",
                    "top_index": top_index,
                    "top_total": len(groups),
                    "title": group.group_title,
                    "pending_count": len(ids_to_summarize),
                }
            )
        group_markdown = _build_group_markdown(lines, group, node_lookup)
        id_to_title = {target_id: node_lookup[target_id].title for target_id in ids_to_summarize}
        try:
            summary_map = summary_provider.summarize_many(
                group_markdown,
                file_path=rel_path,
                top_title=group.group_title,
                id_to_title=id_to_title,
            )
        except SummaryProviderError as exc:
            stats.summary_failures += len(ids_to_summarize)
            if fail_on_summary_error:
                raise
            summary_map = {sec_id: f"AI Summary can't be generated: {exc}" for sec_id in ids_to_summarize}
        for sec_id in ids_to_summarize:
            _set_summary_and_status_by_id(
                converted,
                sec_id,
                summary_map.get(sec_id, "").strip(),
            )
            if not summary_map.get(sec_id, "").strip():
                _set_summary_and_status_by_id(
                    converted,
                    sec_id,
                    "AI Summary can't be generated: empty result for this section id.",
                )
        if progress_cb:
            progress_cb(
                {
                    "type": "top_section_done",
                    "top_index": top_index,
                    "top_total": len(groups),
                    "title": group.group_title,
                }
            )
    return converted


def _build_section_tree(
    section: ParsedSection,
    lines: list[str],
    rel_path: str,
    reuse_lookup: dict[tuple[str, tuple[str, ...], str], tuple[str, str | None]],
    used_ids: set[str],
    slug_counts: dict[str, int],
) -> tuple[SectionNode, dict[str, tuple[str, str]]]:
    content = _section_content(lines, section.start, section.end)
    content_hash = sha256_text(content)
    key = (rel_path, tuple(section.heading_path), content_hash)
    pending: dict[str, tuple[str, str]] = {}
    if key in reuse_lookup:
        section_id, summary = reuse_lookup[key]
        used_ids.add(section_id)
    else:
        base_slug = slugify_title(section.title)
        force_suffix = slug_counts.get(base_slug, 0) > 1
        section_id = section_id_from_title(section.title, used_ids, force_suffix=force_suffix)
        summary = ""
        pending[section_id] = (section.title, content)
    children_nodes: list[SectionNode] = []
    for child in section.children:
        child_node, child_pending = _build_section_tree(
            child,
            lines,
            rel_path,
            reuse_lookup,
            used_ids,
            slug_counts,
        )
        children_nodes.append(child_node)
        pending.update(child_pending)
    node = SectionNode(
        id=section_id,
        title=section.title,
        level=section.level,
        start=section.start,
        end=section.end,
        summary=summary,
        content_hash=content_hash,
        file_path=rel_path,
        heading_path=section.heading_path,
        children=children_nodes,
    )
    return node, pending


def _set_summary_and_status_by_id(nodes: list[SectionNode], section_id: str, summary: str) -> bool:
    for node in nodes:
        if node.id == section_id:
            node.summary = summary
            node.summary_status = "generated" if summary else "error"
            return True
        if _set_summary_and_status_by_id(node.children, section_id, summary):
            return True
    return False


def _count_sections(nodes: list[SectionNode]) -> int:
    total = 0
    for n in nodes:
        total += 1 + _count_sections(n.children)
    return total


def _iter_sections(nodes: list[SectionNode]):
    for node in nodes:
        yield node
        yield from _iter_sections(node.children)


def _section_content(lines: list[str], start: int, end: int) -> str:
    if start <= 0:
        return "\n".join(lines[:end])
    return "\n".join(lines[start - 1 : end])


def _collect_slug_counts(sections: list[ParsedSection]) -> dict[str, int]:
    counts: dict[str, int] = {}

    def walk(nodes: list[ParsedSection]) -> None:
        for node in nodes:
            base = slugify_title(node.title)
            counts[base] = counts.get(base, 0) + 1
            if node.children:
                walk(node.children)

    walk(sections)
    return counts


def _count_parsed_sections(nodes: list[ParsedSection]) -> int:
    total = 0
    for n in nodes:
        total += 1 + _count_parsed_sections(n.children)
    return total


def _build_node_lookup(nodes: list[SectionNode]) -> dict[str, SectionNode]:
    lookup: dict[str, SectionNode] = {}
    for node in nodes:
        lookup[node.id] = node
        lookup.update(_build_node_lookup(node.children))
    return lookup


def _mark_summary_status(nodes: list[SectionNode], target_ids: set[str]) -> None:
    for node in nodes:
        if node.id in target_ids:
            if node.summary:
                node.summary_status = "generated"
            else:
                node.summary_status = "pending"
        else:
            node.summary = None
            node.summary_status = "context_only"
        _mark_summary_status(node.children, target_ids)


def _build_summary_groups(
    roots: list[SectionNode],
    *,
    summary_root_level: int,
    include_excluded_ancestors_as_context: bool,
) -> list[SummaryGroup]:
    groups: dict[str, SummaryGroup] = {}

    def walk(
        node: SectionNode,
        current_summary_root: SectionNode | None,
        current_context_ancestor: SectionNode | None,
    ) -> None:
        if node.level < summary_root_level:
            current_context_ancestor = node
            current_summary_root = None
        if node.level == summary_root_level:
            current_summary_root = node

        is_target = False
        if node.level == summary_root_level:
            is_target = True
        elif node.level > summary_root_level and current_summary_root is not None:
            is_target = True

        if is_target and current_summary_root is not None:
            if include_excluded_ancestors_as_context and current_context_ancestor is not None:
                group_key = current_context_ancestor.id
                group_title = current_context_ancestor.title
                context_id = current_context_ancestor.id
            else:
                group_key = current_summary_root.id
                group_title = current_summary_root.title
                context_id = None

            group = groups.get(group_key)
            if group is None:
                group = SummaryGroup(
                    key=group_key,
                    group_title=group_title,
                    context_ancestor_id=context_id,
                    target_ids=[],
                    top_target_ids=[],
                )
                groups[group_key] = group
            group.target_ids.append(node.id)
            if node.id == current_summary_root.id:
                group.top_target_ids.append(node.id)

        for child in node.children:
            walk(child, current_summary_root, current_context_ancestor)

    for root in roots:
        walk(root, None, None)
    return list(groups.values())


def _build_group_markdown(lines: list[str], group: SummaryGroup, node_lookup: dict[str, SectionNode]) -> str:
    blocks: list[str] = []
    if group.context_ancestor_id:
        context_node = node_lookup[group.context_ancestor_id]
        if group.top_target_ids:
            first_top_start = min(node_lookup[top_id].start for top_id in group.top_target_ids)
            context_end = max(context_node.start, first_top_start - 1)
            blocks.append(_section_content(lines, context_node.start, context_end))
    for top_id in group.top_target_ids:
        top_node = node_lookup[top_id]
        blocks.append(_section_content(lines, top_node.start, top_node.end))
    return "\n\n".join([b for b in blocks if b.strip()])
