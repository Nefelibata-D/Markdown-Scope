from __future__ import annotations

from pathlib import Path
from typing import Callable

from .index_builder import BuildOptions, build_index, build_reuse_lookup
from .index_models import RootIndex
from .summary.providers import SummaryProvider


def update_index(
    root: Path,
    old_index: RootIndex,
    provider: SummaryProvider,
    include_patterns: list[str] | None = None,
    progress_cb: Callable[[dict], None] | None = None,
    summary_root_level: int | None = None,
    include_excluded_ancestors_as_context: bool | None = None,
) -> RootIndex:
    reuse = build_reuse_lookup(old_index)
    first_file = old_index.files[0] if old_index.files else None
    options = BuildOptions(
        root=root,
        include_patterns=include_patterns,
        fail_on_summary_error=False,
        progress_cb=progress_cb,
        summary_root_level=summary_root_level if summary_root_level is not None else (first_file.summary_root_level if first_file else 2),
        include_excluded_ancestors_as_context=(
            include_excluded_ancestors_as_context
            if include_excluded_ancestors_as_context is not None
            else (first_file.include_excluded_ancestors_as_context if first_file else True)
        ),
    )
    return build_index(options, provider, existing_reuse_lookup=reuse)
