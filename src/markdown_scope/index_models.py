from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class SectionNode(BaseModel):
    id: str
    title: str
    level: int
    start: int
    end: int
    summary: str | None = None
    summary_status: str | None = None
    content_hash: str
    file_path: str
    heading_path: list[str] = Field(default_factory=list)
    children: list["SectionNode"] = Field(default_factory=list)


class FileIndex(BaseModel):
    path: str
    sha256: str
    line_count: int
    summary_root_level: int = 2
    include_excluded_ancestors_as_context: bool = True
    sections: list[SectionNode] = Field(default_factory=list)


class IndexStats(BaseModel):
    file_count: int = 0
    section_count: int = 0
    summary_failures: int = 0


class RootIndex(BaseModel):
    version: str = "1.0"
    root_path: str
    indexed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provider: str = "mock"
    files: list[FileIndex] = Field(default_factory=list)
    stats: IndexStats = Field(default_factory=IndexStats)

    def model_dump_jsonable(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PublicSection(BaseModel):
    id: str
    title: str
    level: int
    start: int
    end: int
    summary: str | None = None
    summary_status: str | None = None
    children: list["PublicSection"] = Field(default_factory=list)


class PublicFileIndex(BaseModel):
    file_name: str
    path: str
    line_count: int
    summary_root_level: int = 2
    include_excluded_ancestors_as_context: bool = True
    sections: list[PublicSection] = Field(default_factory=list)


class PublicIndex(BaseModel):
    files: list[PublicFileIndex] = Field(default_factory=list)
