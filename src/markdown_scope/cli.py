from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Optional

import typer

from .config import cfg_path, cfg_value, load_config
from .exceptions import MDScopeError
from .index_builder import BuildOptions, build_index
from .index_updater import update_index
from .reader import read_lines, read_section, read_sections_contextual
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
        text = data if isinstance(data, str) else str(data)
        try:
            typer.echo(text)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or "utf-8"
            safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
            typer.echo(safe)
    elif output_format == "markdown":
        text = data if isinstance(data, str) else str(data)
        try:
            typer.echo(text)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or "utf-8"
            safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
            typer.echo(safe)
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
                f"  |- lines: {event['line_count']}, sections: {event['section_count']}, top-level: {event['top_level_count']}",
                err=True,
            )
        elif event_type == "top_section_start":
            typer.echo(
                f"  |- [{event['top_index']}/{event['top_total']}] summarize top-section: {event['title']} (pending={event['pending_count']})",
                err=True,
            )
        elif event_type == "top_section_done":
            typer.echo(
                f"  |  `- done: {event['title']}",
                err=True,
            )
        elif event_type == "file_done":
            typer.echo("  `- file done", err=True)

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


def _list_md_files(root: Path, target: str | None = None) -> list[str]:
    base = root
    if target:
        base = root / target
    if not base.exists():
        raise typer.BadParameter(f"Target path not found: {base}")
    if base.is_file():
        return [base.relative_to(root).as_posix()] if base.suffix.lower() == ".md" else []
    return sorted([p.relative_to(root).as_posix() for p in base.rglob("*.md") if p.is_file()])


@app.command("build")
def build_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    index: Optional[Path] = typer.Option(None, help="Index output path, defaults to ROOT/.md-scope-index.json"),
    overwrite: Optional[bool] = typer.Option(None, help="Overwrite existing index file."),
    include: Optional[list[str]] = typer.Option(None, help="Glob patterns under root, e.g. '*.md' or 'references/**/*.md'."),
    provider: Optional[str] = typer.Option(None, help="Summary provider: openai-compatible"),
    api_base: Optional[str] = typer.Option(None, help="OpenAI compatible base URL"),
    api_key: Optional[str] = typer.Option(None, help="API key"),
    model: Optional[str] = typer.Option(None, help="Model name"),
    api_timeout_seconds: Optional[float] = typer.Option(None, help="AI request timeout in seconds."),
    api_requests_per_minute: Optional[int] = typer.Option(None, help="Max AI requests per minute."),
    system_prompt: Optional[str] = typer.Option(None, help="AI system prompt."),
    user_prompt: Optional[str] = typer.Option(None, help="AI user prompt template."),
    summary_root_level: Optional[int] = typer.Option(None, help="Summary root heading level, default 2."),
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
    api_timeout_seconds = cfg_value(cfg, "api_timeout_seconds", api_timeout_seconds, 30.0)
    api_requests_per_minute = cfg_value(cfg, "api_requests_per_minute", api_requests_per_minute, None)
    system_prompt = cfg_value(cfg, "system_prompt", system_prompt, None)
    user_prompt = cfg_value(cfg, "user_prompt", user_prompt, None)
    summary_root_level = int(cfg_value(cfg, "summary_root_level", summary_root_level, 2))
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
        timeout_seconds=float(api_timeout_seconds),
        requests_per_minute=int(api_requests_per_minute) if api_requests_per_minute is not None else None,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    built = build_index(
        BuildOptions(
            root=root,
            include_patterns=include,
            progress_cb=_build_progress_cb(),
            summary_root_level=summary_root_level,
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
    index: Optional[Path] = typer.Option(None, help="Index path, defaults to ROOT/.md-scope-index.json"),
    include: Optional[list[str]] = typer.Option(None, help="Glob patterns under root."),
    provider: Optional[str] = typer.Option(None, help="Summary provider: openai-compatible"),
    api_base: Optional[str] = typer.Option(None),
    api_key: Optional[str] = typer.Option(None),
    model: Optional[str] = typer.Option(None),
    api_timeout_seconds: Optional[float] = typer.Option(None, help="AI request timeout in seconds."),
    api_requests_per_minute: Optional[int] = typer.Option(None, help="Max AI requests per minute."),
    system_prompt: Optional[str] = typer.Option(None),
    user_prompt: Optional[str] = typer.Option(None),
    summary_root_level: Optional[int] = typer.Option(None, help="Summary root heading level, default 2."),
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
    api_timeout_seconds = cfg_value(cfg, "api_timeout_seconds", api_timeout_seconds, 30.0)
    api_requests_per_minute = cfg_value(cfg, "api_requests_per_minute", api_requests_per_minute, None)
    system_prompt = cfg_value(cfg, "system_prompt", system_prompt, None)
    user_prompt = cfg_value(cfg, "user_prompt", user_prompt, None)
    summary_root_level = cfg_value(cfg, "summary_root_level", summary_root_level, None)
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
        timeout_seconds=float(api_timeout_seconds),
        requests_per_minute=int(api_requests_per_minute) if api_requests_per_minute is not None else None,
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
        include_excluded_ancestors_as_context=include_excluded_ancestors_as_context,
    )
    write_index(idx_path, updated)
    write_lock_index(lock_path, updated)
    typer.echo(f"Update finished. index={idx_path} lock={lock_path}", err=True)
    _emit({"index_path": str(idx_path), "stats": updated.stats.model_dump(), "provider": updated.provider}, output_format)


def _outline_impl(
    *,
    config: Optional[Path],
    root: Optional[Path],
    index: Optional[Path],
    target: Optional[str],
    full: bool,
    with_summary: bool,
    output_format: Optional[str],
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
        _emit(render_tree_text(view_data, with_summary=with_summary), "text")
    elif output_format == "markdown":
        _emit(render_catalog_markdown(view_data, with_summary=with_summary), "markdown")
    else:
        raise typer.BadParameter("format must be json|text|markdown")


@app.command("outline")
def outline_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    index: Optional[Path] = typer.Option(None),
    target: Optional[str] = typer.Option(None, help="Relative file or directory under root/index scope"),
    full: bool = typer.Option(False, help="Only for JSON: include line_count/level/start/end."),
    with_summary: bool = typer.Option(
        False,
        "--with_summary",
        "--with-summary",
        help="Include summary text in text/markdown output.",
    ),
    output_format: Optional[str] = typer.Option(None, "--format"),
) -> None:
    _outline_impl(
        config=config,
        root=root,
        index=index,
        target=target,
        full=full,
        with_summary=with_summary,
        output_format=output_format,
    )


@app.command("catalog")
def catalog_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    index: Optional[Path] = typer.Option(None),
    target: Optional[str] = typer.Option(None, help="Relative file or directory under root/index scope"),
    full: bool = typer.Option(False, help="Only for JSON: include line_count/level/start/end."),
    with_summary: bool = typer.Option(
        False,
        "--with_summary",
        "--with-summary",
        help="Include summary text in text/markdown output.",
    ),
    output_format: Optional[str] = typer.Option(None, "--format"),
) -> None:
    _outline_impl(
        config=config,
        root=root,
        index=index,
        target=target,
        full=full,
        with_summary=with_summary,
        output_format=output_format,
    )


@app.command("view", hidden=True)
def view_alias_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    index: Optional[Path] = typer.Option(None),
    target: Optional[str] = typer.Option(None, help="Relative file or directory under root/index scope"),
    full: bool = typer.Option(False, help="Only for JSON: include line_count/level/start/end."),
    with_summary: bool = typer.Option(
        False,
        "--with_summary",
        "--with-summary",
        help="Include summary text in text/markdown output.",
    ),
    output_format: Optional[str] = typer.Option(None, "--format"),
) -> None:
    _outline_impl(
        config=config,
        root=root,
        index=index,
        target=target,
        full=full,
        with_summary=with_summary,
        output_format=output_format,
    )


@app.command("search")
def search_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    query: str = typer.Option(...),
    index: Optional[Path] = typer.Option(None),
    field: Optional[str] = typer.Option(None, help="all|title|path|summary"),
    target: Optional[str] = typer.Option(None, help="Limit to file or directory target"),
    full: bool = typer.Option(False, help="Only for JSON: include line_count/level/start/end."),
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
    section_ids: list[str] = typer.Option(..., "--id"),
    index: Optional[Path] = typer.Option(None),
    max_lines: Optional[int] = typer.Option(None),
    mode: str = typer.Option("simple", help="Read mode: simple|contextual"),
    output_format: Optional[str] = typer.Option(None, "--format"),
) -> None:
    cfg = load_config(config)
    root = _require_root(cfg_path(cfg, "root", root))
    index = cfg_path(cfg, "index", index)
    max_lines = int(cfg_value(cfg, "max_lines", max_lines, 600))
    mode = cfg_value(cfg, "mode", mode, "simple")
    output_format = cfg_value(cfg, "format", output_format, "json")
    if mode not in {"simple", "contextual"}:
        raise typer.BadParameter("mode must be simple|contextual")

    idx = read_index(_resolve_index_path(root, index))
    if mode == "contextual":
        payload = read_sections_contextual(idx, root, section_ids, max_lines=max_lines)
        if output_format == "text":
            if "files" in payload:
                chunks: list[str] = []
                for file_payload in payload["files"]:
                    chunks.append(f"[file: {file_payload['file_name']}]\n{file_payload['content']}")
                _emit("\n\n".join(chunks), "text")
            else:
                _emit(payload["content"], "text")
        else:
            _emit(payload, "json")
        return

    payloads: list[dict] = []
    errors: list[dict] = []
    for section_id in section_ids:
        try:
            payloads.append(
                read_section(
                    idx,
                    root,
                    section_id,
                    max_lines=max_lines,
                )
            )
        except MDScopeError as exc:
            errors.append({"id": section_id, "error": str(exc)})

    if len(section_ids) == 1 and errors:
        raise MDScopeError(errors[0]["error"])

    if output_format == "text":
        if len(section_ids) == 1 and len(payloads) == 1 and not errors:
            _emit(payloads[0]["content"], "text")
        else:
            chunks = [f"## {p['id']} ({p['title']})\nfile: {p['file_name']}\n{p['content']}" for p in payloads]
            if errors:
                chunks.extend([f"## {item['id']} (error)\n{item['error']}" for item in errors])
            _emit("\n\n".join(chunks), "text")
    else:
        if len(section_ids) == 1:
            _emit(payloads[0], "json")
        else:
            _emit({"results": payloads, "errors": errors}, "json")


@app.command("md-files")
def md_files_cmd(
    config: Optional[Path] = typer.Option(None, help="Path to TOML config file"),
    root: Optional[Path] = typer.Option(None, help="Markdown root directory"),
    target: Optional[str] = typer.Option(None, help="Optional subdirectory under root."),
    output_format: Optional[str] = typer.Option(None, "--format"),
) -> None:
    cfg = load_config(config)
    root = _require_root(cfg_path(cfg, "root", root))
    target = cfg_value(cfg, "target", target, None)
    output_format = cfg_value(cfg, "format", output_format, "json")

    files = _list_md_files(root, target=target)
    payload = {
        "root": str(root),
        "target": target,
        "md_files": [{"path": f, "type": "markdown", "viewable_by_tool": True} for f in files],
    }
    if output_format == "json":
        _emit(payload, "json")
    elif output_format == "text":
        _emit("\n".join(files) if files else "(no markdown files)", "text")
    elif output_format == "markdown":
        lines = ["# Markdown Files", ""]
        lines.extend([f"- `{f}`" for f in files] if files else ["- _none_"])
        _emit("\n".join(lines), "markdown")
    else:
        raise typer.BadParameter("format must be json|text|markdown")


@app.callback()
def _main() -> None:
    """Main callback."""


def run() -> int:
    try:
        app()
        return 0
    except MDScopeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
