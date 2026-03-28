from __future__ import annotations

from .exceptions import ScopePathError
from .index_models import PublicFileIndex, PublicIndex


def select_view(index: PublicIndex, target: str | None = None) -> dict:
    files = index.files
    selected_target = target
    if selected_target is None:
        if any(f.file_name == "SKILL.md" for f in files):
            selected_target = "SKILL.md"
    if selected_target:
        selected = _filter_files(files, selected_target)
    else:
        selected = files
    return {
        "target": selected_target,
        "files": [f.model_dump(mode="json") for f in selected],
    }


def _filter_files(files: list[PublicFileIndex], target: str) -> list[PublicFileIndex]:
    norm = target.replace("\\", "/").strip("/")
    if not norm:
        return files
    if norm.endswith(".md"):
        matched = [f for f in files if f.file_name == norm]
        if not matched:
            raise ScopePathError(f"File target '{target}' not found in index scope.")
        return matched
    prefix = norm + "/"
    matched = [f for f in files if f.file_name.startswith(prefix)]
    if not matched:
        raise ScopePathError(f"Directory target '{target}' not found in index scope.")
    return matched


def render_tree_text(view_data: dict, *, with_summary: bool = False) -> str:
    lines: list[str] = []
    for file in view_data["files"]:
        lines.append(f"{file['file_name']}")
        for section in file["sections"]:
            _render_section_text(section, lines, depth=1, with_summary=with_summary)
    return "\n".join(lines)


def _render_section_text(section: dict, lines: list[str], depth: int, *, with_summary: bool) -> None:
    indent = "  " * depth
    lines.append(
        f"{indent}- {section['title']} (line: [{section['start']}-{section['end']}]  | id: {section['id']} )"
    )
    summary = (section.get("summary") or "").replace("\n", " ").strip()
    if with_summary and summary:
        lines.append(f"{indent}  summary: {summary}")
    for child in section["children"]:
        _render_section_text(child, lines, depth + 1, with_summary=with_summary)


def render_catalog_markdown(
    view_data: dict,
    title: str = "Markdown Scope Catalog",
    *,
    with_summary: bool = False,
) -> str:
    lines: list[str] = [f"# {title}", ""]
    for file in view_data["files"]:
        lines.append(f"## File: `{file['file_name']}`")
        lines.append("")
        if not file["sections"]:
            lines.append("_No sections_")
            lines.append("")
            continue
        for section in file["sections"]:
            _render_section_markdown(section, lines, depth=0, with_summary=with_summary)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_section_markdown(section: dict, lines: list[str], depth: int, *, with_summary: bool) -> None:
    bullet_indent = "  " * depth
    summary = (section.get("summary") or "").replace("\n", " ").strip()
    lines.append(
        f"{bullet_indent}- **{section['title']}**  "
        f"(id: `{section['id']}`, lines: `{section['start']}-{section['end']}`)"
    )
    if with_summary:
        lines.append(f"{bullet_indent}  - summary: {summary}")
    for child in section["children"]:
        _render_section_markdown(child, lines, depth + 1, with_summary=with_summary)
