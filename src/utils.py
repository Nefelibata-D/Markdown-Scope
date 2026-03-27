from __future__ import annotations

import hashlib
import json
import re
import secrets
from pathlib import Path
from typing import Any

from .exceptions import IndexNotFoundError, ScopePathError
from .index_models import PublicFileIndex, PublicIndex, PublicSection, RootIndex, SectionNode


DEFAULT_INDEX_NAME = ".mdx-index.json"
DEFAULT_LOCK_NAME = ".mdx-index.lock.json"


def default_index_path(root: Path) -> Path:
    return root / DEFAULT_INDEX_NAME


def default_lock_path(root: Path) -> Path:
    return root / DEFAULT_LOCK_NAME


def ensure_in_scope(root: Path, target: Path) -> Path:
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ScopePathError(f"Path '{target}' is outside root '{root}'.") from exc
    return target_resolved


def relative_posix(root: Path, target: Path) -> str:
    return ensure_in_scope(root, target).relative_to(root.resolve()).as_posix()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def section_id_from_title(title: str, used_ids: set[str], *, force_suffix: bool = False) -> str:
    base = slugify_title(title)
    if force_suffix:
        while True:
            suffix = secrets.token_hex(2)
            candidate = f"{base}-{suffix}"
            if candidate not in used_ids:
                used_ids.add(candidate)
                return candidate

    candidate = base
    if candidate in used_ids:
        while True:
            suffix = secrets.token_hex(2)
            candidate = f"{base}-{suffix}"
            if candidate not in used_ids:
                break
    used_ids.add(candidate)
    return candidate


def slugify_title(title: str) -> str:
    lowered = title.strip().lower()
    lowered = re.sub(r"[^\w\s-]", "", lowered)
    lowered = re.sub(r"[\s_]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered or "section"


def write_index(path: Path, index: RootIndex) -> None:
    public_index = to_public_index(index)
    path.parent.mkdir(parents=True, exist_ok=True)
    wire = _public_index_to_wire(public_index)
    path.write_text(json.dumps(wire, ensure_ascii=False, indent=2), encoding="utf-8")


def write_lock_index(path: Path, index: RootIndex) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index.model_dump_jsonable(), ensure_ascii=False, indent=2), encoding="utf-8")


def read_index(path: Path) -> PublicIndex:
    if not path.exists():
        raise IndexNotFoundError(f"Index file not found: {path}")
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IndexNotFoundError(f"Index file is corrupted: {path}") from exc
    normalized = _wire_to_public_index_data(data)
    return PublicIndex.model_validate(normalized)


def read_lock_index(path: Path) -> RootIndex:
    if not path.exists():
        raise IndexNotFoundError(f"Lock file not found: {path}")
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IndexNotFoundError(f"Lock file is corrupted: {path}") from exc
    return RootIndex.model_validate(data)


def to_public_index(index: RootIndex) -> PublicIndex:
    files: list[PublicFileIndex] = []
    for file in index.files:
        files.append(
            PublicFileIndex(
                file_name=file.path,
                line_count=file.line_count,
                summary_root_level=file.summary_root_level,
                summary_exclude_levels=file.summary_exclude_levels,
                include_excluded_ancestors_as_context=file.include_excluded_ancestors_as_context,
                sections=[_to_public_section(s) for s in file.sections],
            )
        )
    return PublicIndex(files=files)


def _to_public_section(section: SectionNode) -> PublicSection:
    return PublicSection(
        id=section.id,
        title=section.title,
        level=section.level,
        start=section.start,
        end=section.end,
        summary=section.summary,
        summary_status=section.summary_status,
        children=[_to_public_section(c) for c in section.children],
    )


def _public_index_to_wire(index: PublicIndex) -> dict[str, Any]:
    payload = index.model_dump(mode="json")
    for file in payload.get("files", []):
        if "file_name" in file:
            file["file-name"] = file.pop("file_name")
    return payload


def _wire_to_public_index_data(data: dict[str, Any]) -> dict[str, Any]:
    files = data.get("files", [])
    if isinstance(files, list):
        for file in files:
            if isinstance(file, dict) and "file-name" in file and "file_name" not in file:
                file["file_name"] = file.pop("file-name")
    return data
