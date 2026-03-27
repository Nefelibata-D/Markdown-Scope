from __future__ import annotations

from .index_models import PublicIndex, PublicSection


def search_index(
    index: PublicIndex,
    query: str,
    *,
    field: str = "all",
    target: str | None = None,
) -> list[dict]:
    q = query.lower().strip()
    if not q:
        return []
    matcher = _build_matcher(field, q)
    target_prefix, target_exact = _normalize_target(target)
    results: list[dict] = []

    for file in index.files:
        if not _file_in_scope(file.file_name, target_prefix, target_exact):
            continue
        for section in _iter_sections(file.sections):
            if matcher(section, file.file_name):
                results.append(
                    {
                        "file_name": file.file_name,
                        "line_count": file.line_count,
                        "id": section.id,
                        "title": section.title,
                        "level": section.level,
                        "start": section.start,
                        "end": section.end,
                        "summary": section.summary,
                    }
                )
    return results


def _build_matcher(field: str, query: str):
    if field == "title":
        return lambda s, _p: query in s.title.lower()
    if field == "path":
        return lambda _s, p: query in p.lower()
    if field == "summary":
        return lambda s, _p: query in s.summary.lower()
    return lambda s, p: query in s.title.lower() or query in p.lower() or query in s.summary.lower()


def _normalize_target(target: str | None) -> tuple[str | None, str | None]:
    if not target:
        return None, None
    t = target.replace("\\", "/").strip("/")
    if not t:
        return None, None
    if t.endswith(".md"):
        return None, t
    return t + "/", None


def _file_in_scope(path: str, prefix: str | None, exact: str | None) -> bool:
    if exact:
        return path == exact
    if prefix:
        return path.startswith(prefix)
    return True


def _iter_sections(nodes: list[PublicSection]):
    for node in nodes:
        yield node
        yield from _iter_sections(node.children)
