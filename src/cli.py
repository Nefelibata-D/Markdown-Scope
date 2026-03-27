from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from .config import cfg_path, cfg_value, load_config
from .exceptions import MDScopeError
from .index_builder import BuildOptions, build_index
from .index_updater import update_index
from .reader import read_lines, read_section
from .searcher import search_index
from .summary.providers import provider_from_name
from .utils import (
    default_index_path,
    default_lock_path,
    read_index,
    read_lock_index,
    relative_posix,
    write_index,
    write_lock_index,
)
from .viewer import render_catalog_markdown, render_tree_text, select_view

app = typer.Typer(help="markdown-scope CLI: build structured markdown index and read selectively.")


def _emit(data, output_format: str = "json") -> None:
    if output_format == "json":
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
    elif output_format == "text":
        typer.echo(data if isinstance(data, str) else str(data))
    elif output_format == "markdown":
        typer.echo(data if isinstance(data, str) else str(data))
    else:
        raise typer.BadParameter(f"Unsupported format: {output_format}")


def _resolve_index_path(root: Path, index: Optional[Path]) -> Path:
    return index if index else default_index_path(root)


def _resolve_lock_path(root: Path, lock: Optional[Path]) -> Path:
    return lock if lock else default_lock_path(root)


def _require_root(root: Path | None) -> Path:
    if root is None:
        raise typer.BadParameter("Root directory is required. Pass --root or set it in config.")
    if not root.exists() or not root.is_dir():
        raise typer.BadParameter(f"Root directory does not exist: {root}")
    return root


def _build_progress_cb():
    def cb(event: dict) -> None:
        event_type = event.get("type")
        if event_type == "file_start":
            typer.echo(
                f"[{event['file_index']}/{event['file_total']}] {event['file_path']}",
                err=True,
            )
            typer.echo(
                f"  ├─ lines: {event['line_count']}, sections: {event['section_count']}, top-level: {event['top_level_count']}",
                err=True,
            )
        elif event_type == "top_section_start":
            typer.echo(
                f"  ├─ [{event['top_index']}/{event['top_total']}] summarize top-section: {event['title']} (pending={event['pending_count']})",
                err=True,
            )
        elif event_type == "top_section_done":
            typer.echo(
                f"  │  └─ done: {event['title']}",
                err=True,
            )
        elif event_type == "file_done":
            typer.echo("  └─ file done", err=True)

    return cb


def _compact_sections(file_name: str, line_count: int, sections: list[dict], full: bool) -> list[dict]:
    rows: list[dict] = []
    for section in sections:
        row = {
            "file-name": file_name,
            "id": section["id"],
            "title": section["title"],
            "summary": section["summary"],
        }
        if full:
            row.update(
                {
                    "line_count": line_count,
                    "level": section["level"],
                    "start": section["start"],
                    "end": section["end"],
                }
            )
        rows.append(row)
        rows.extend(_compact_sections(file_name, line_count, section.get("children", []), full))
    return rows


@app.command("build")
def build_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    index: Optional[Path] = typer.Option(None, help="Index output path, defaults to ROOT/.mdx-index.json"),
    overwrite: Optional[bool] = typer.Option(None, help="Overwrite existing index file."),
    include: Optional[list[str]] = typer.Option(None, help="Glob patterns under root, e.g. '*.md' or 'reference/**/*.md'."),
    provider: Optional[str] = typer.Option(None, help="Summary provider: openai-compatible"),
    api_base: Optional[str] = typer.Option(None, help="OpenAI compatible base URL"),
    api_key: Optional[str] = typer.Option(None, help="API key"),
    model: Optional[str] = typer.Option(None, help="Model name"),
    system_prompt: Optional[str] = typer.Option(None, help="AI system prompt."),
    user_prompt: Optional[str] = typer.Option(None, help="AI user prompt template."),
    summary_root_level: Optional[int] = typer.Option(None, help="Summary root heading level, default 2."),
    summary_exclude_levels: Optional[list[int]] = typer.Option(None, help="Heading levels used as context only."),
    include_excluded_ancestors_as_context: Optional[bool] = typer.Option(
        None, help="Include excluded ancestors as context in AI request."
    ),
    output_format: Optional[str] = typer.Option(None, "--format"),
) -> None:
    cfg = load_config(config)
    root = _require_root(cfg_path(cfg, "root", root))
    index = cfg_path(cfg, "index", index)
    overwrite = bool(cfg_value(cfg, "overwrite", overwrite, False))
    include = cfg_value(cfg, "include", include, None)
    provider = cfg_value(cfg, "provider", provider, "openai-compatible")
    api_base = cfg_value(cfg, "api_base", api_base, None)
    api_key = cfg_value(cfg, "api_key", api_key, None)
    model = cfg_value(cfg, "model", model, None)
    system_prompt = cfg_value(cfg, "system_prompt", system_prompt, None)
    user_prompt = cfg_value(cfg, "user_prompt", user_prompt, None)
    summary_root_level = int(cfg_value(cfg, "summary_root_level", summary_root_level, 2))
    summary_exclude_levels = cfg_value(cfg, "summary_exclude_levels", summary_exclude_levels, [1])
    include_excluded_ancestors_as_context = bool(
        cfg_value(cfg, "include_excluded_ancestors_as_context", include_excluded_ancestors_as_context, True)
    )
    output_format = cfg_value(cfg, "format", output_format, "json")
    lock_path = _resolve_lock_path(root, None)

    idx_path = _resolve_index_path(root, index)
    if idx_path.exists() and not overwrite:
        raise typer.BadParameter(f"Index already exists: {idx_path}. Use --overwrite to replace it.")
    summary_provider = provider_from_name(
        provider,
        api_base=api_base,
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    built = build_index(
        BuildOptions(
            root=root,
            include_patterns=include,
            progress_cb=_build_progress_cb(),
            summary_root_level=summary_root_level,
            summary_exclude_levels=summary_exclude_levels,
            include_excluded_ancestors_as_context=include_excluded_ancestors_as_context,
        ),
        summary_provider,
    )
    write_index(idx_path, built)
    write_lock_index(lock_path, built)
    typer.echo(f"Build finished. index={idx_path} lock={lock_path}", err=True)
    _emit({"index_path": str(idx_path), "stats": built.stats.model_dump(), "provider": built.provider}, output_format)


@app.command("update")
def update_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    index: Optional[Path] = typer.Option(None, help="Index path, defaults to ROOT/.mdx-index.json"),
    include: Optional[list[str]] = typer.Option(None, help="Glob patterns under root."),
    provider: Optional[str] = typer.Option(None, help="Summary provider: openai-compatible"),
    api_base: Optional[str] = typer.Option(None),
    api_key: Optional[str] = typer.Option(None),
    model: Optional[str] = typer.Option(None),
    system_prompt: Optional[str] = typer.Option(None),
    user_prompt: Optional[str] = typer.Option(None),
    summary_root_level: Optional[int] = typer.Option(None, help="Summary root heading level, default 2."),
    summary_exclude_levels: Optional[list[int]] = typer.Option(None, help="Heading levels used as context only."),
    include_excluded_ancestors_as_context: Optional[bool] = typer.Option(
        None, help="Include excluded ancestors as context in AI request."
    ),
    output_format: Optional[str] = typer.Option(None, "--format"),
) -> None:
    cfg = load_config(config)
    root = _require_root(cfg_path(cfg, "root", root))
    index = cfg_path(cfg, "index", index)
    include = cfg_value(cfg, "include", include, None)
    provider = cfg_value(cfg, "provider", provider, "openai-compatible")
    api_base = cfg_value(cfg, "api_base", api_base, None)
    api_key = cfg_value(cfg, "api_key", api_key, None)
    model = cfg_value(cfg, "model", model, None)
    system_prompt = cfg_value(cfg, "system_prompt", system_prompt, None)
    user_prompt = cfg_value(cfg, "user_prompt", user_prompt, None)
    summary_root_level = cfg_value(cfg, "summary_root_level", summary_root_level, None)
    summary_exclude_levels = cfg_value(cfg, "summary_exclude_levels", summary_exclude_levels, None)
    include_excluded_ancestors_as_context = cfg_value(
        cfg,
        "include_excluded_ancestors_as_context",
        include_excluded_ancestors_as_context,
        None,
    )
    output_format = cfg_value(cfg, "format", output_format, "json")
    lock_path = _resolve_lock_path(root, None)

    idx_path = _resolve_index_path(root, index)
    old_lock = read_lock_index(lock_path)
    summary_provider = provider_from_name(
        provider,
        api_base=api_base,
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    updated = update_index(
        root,
        old_lock,
        summary_provider,
        include_patterns=include,
        progress_cb=_build_progress_cb(),
        summary_root_level=summary_root_level,
        summary_exclude_levels=summary_exclude_levels,
        include_excluded_ancestors_as_context=include_excluded_ancestors_as_context,
    )
    write_index(idx_path, updated)
    write_lock_index(lock_path, updated)
    typer.echo(f"Update finished. index={idx_path} lock={lock_path}", err=True)
    _emit({"index_path": str(idx_path), "stats": updated.stats.model_dump(), "provider": updated.provider}, output_format)


@app.command("view")
def view_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    index: Optional[Path] = typer.Option(None),
    target: Optional[str] = typer.Option(None, help="Relative file or directory under root/index scope"),
    full: bool = typer.Option(False, help="Include line_count/level/start/end fields in JSON output."),
    output_format: Optional[str] = typer.Option(None, "--format"),
) -> None:
    cfg = load_config(config)
    root = _require_root(cfg_path(cfg, "root", root))
    index = cfg_path(cfg, "index", index)
    target = cfg_value(cfg, "target", target, None)
    output_format = cfg_value(cfg, "format", output_format, "json")

    idx_path = _resolve_index_path(root, index)
    idx = read_index(idx_path)
    view_data = select_view(idx, target=target)
    if output_format == "json":
        rows: list[dict] = []
        for file in view_data["files"]:
            rows.extend(_compact_sections(file["file_name"], file["line_count"], file["sections"], full))
        _emit(rows, "json")
    elif output_format == "text":
        _emit(render_tree_text(view_data), "text")
    elif output_format == "markdown":
        _emit(render_catalog_markdown(view_data), "markdown")
    else:
        raise typer.BadParameter("format must be json|text|markdown")


@app.command("search")
def search_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    query: str = typer.Option(...),
    index: Optional[Path] = typer.Option(None),
    field: Optional[str] = typer.Option(None, help="all|title|path|summary"),
    target: Optional[str] = typer.Option(None, help="Limit to file or directory target"),
    full: bool = typer.Option(False, help="Include line_count/level/start/end fields in JSON output."),
    output_format: Optional[str] = typer.Option(None, "--format"),
) -> None:
    cfg = load_config(config)
    root = _require_root(cfg_path(cfg, "root", root))
    index = cfg_path(cfg, "index", index)
    field = cfg_value(cfg, "field", field, "all")
    target = cfg_value(cfg, "target", target, None)
    output_format = cfg_value(cfg, "format", output_format, "json")

    idx = read_index(_resolve_index_path(root, index))
    results = search_index(idx, query, field=field, target=target)
    if output_format == "json":
        compact: list[dict] = []
        for item in results:
            row = {
                "file-name": item["file_name"],
                "id": item["id"],
                "title": item["title"],
                "summary": item["summary"],
            }
            if full:
                row.update(
                    {
                        "line_count": item["line_count"],
                        "level": item["level"],
                        "start": item["start"],
                        "end": item["end"],
                    }
                )
            compact.append(row)
        _emit(compact, "json")
    else:
        _emit(results, output_format)


@app.command("read-lines")
def read_lines_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    file: str = typer.Option(..., help="Relative markdown file path under root"),
    start: int = typer.Option(...),
    end: int = typer.Option(...),
    max_lines: Optional[int] = typer.Option(None),
    output_format: Optional[str] = typer.Option(None, "--format"),
) -> None:
    cfg = load_config(config)
    root = _require_root(cfg_path(cfg, "root", root))
    max_lines = int(cfg_value(cfg, "max_lines", max_lines, 400))
    output_format = cfg_value(cfg, "format", output_format, "json")

    file_path = root / file
    rel = relative_posix(root, file_path)
    payload = read_lines(root / rel, start, end, max_lines=max_lines)
    if output_format == "text":
        _emit(payload["content"], "text")
    else:
        _emit(payload, "json")


@app.command("read-section")
def read_section_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    section_id: str = typer.Option(..., "--id"),
    index: Optional[Path] = typer.Option(None),
    max_lines: Optional[int] = typer.Option(None),
    output_format: Optional[str] = typer.Option(None, "--format"),
) -> None:
    cfg = load_config(config)
    root = _require_root(cfg_path(cfg, "root", root))
    index = cfg_path(cfg, "index", index)
    max_lines = int(cfg_value(cfg, "max_lines", max_lines, 600))
    output_format = cfg_value(cfg, "format", output_format, "json")

    idx = read_index(_resolve_index_path(root, index))
    payload = read_section(idx, root, section_id, max_lines=max_lines)
    if output_format == "text":
        _emit(payload["content"], "text")
    else:
        _emit(payload, "json")


@app.command("export-md")
def export_md_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    index: Optional[Path] = typer.Option(None),
    target: Optional[str] = typer.Option(None),
    output: Optional[Path] = typer.Option(None, help="Output markdown file path"),
) -> None:
    cfg = load_config(config)
    root = _require_root(cfg_path(cfg, "root", root))
    index = cfg_path(cfg, "index", index)
    target = cfg_value(cfg, "target", target, None)
    output = cfg_path(cfg, "output", output)

    idx = read_index(_resolve_index_path(root, index))
    view_data = select_view(idx, target=target)
    md = render_catalog_markdown(view_data)
    if output:
        output.write_text(md, encoding="utf-8")
        typer.echo(str(output))
    else:
        typer.echo(md)


@app.callback()
def _main() -> None:
    """Main callback."""


def run() -> int:
    try:
        app()
        return 0
    except MDScopeError as exc:
        typer.echo(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
