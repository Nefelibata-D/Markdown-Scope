from pathlib import Path

from md_scope.index_builder import BuildOptions, build_index
from md_scope.summary.providers import SummaryProvider


class RecordingProvider:
    name = "recording"

    def __init__(self):
        self.calls = []

    def summarize_many(self, section_text: str, *, file_path: str, top_title: str, id_to_title: dict[str, str]) -> dict[str, str]:
        self.calls.append(
            {
                "section_text": section_text,
                "file_path": file_path,
                "top_title": top_title,
                "id_to_title": dict(id_to_title),
            }
        )
        return {sec_id: f"summary:{title}" for sec_id, title in id_to_title.items()}


def _collect_nodes(file_index):
    nodes = {}

    def walk(items):
        for item in items:
            nodes[item.title] = item
            walk(item.children)

    walk(file_index.sections)
    return nodes


def test_summary_view_keeps_raw_tree_and_context_only_level_1(tmp_path: Path):
    root = tmp_path
    (root / "demo.md").write_text(
        "# A\nintro\n## B\nb\n## C\nc\n# D\n## E\ne\n### F\nf\n",
        encoding="utf-8",
    )
    provider = RecordingProvider()
    idx = build_index(
        BuildOptions(
            root=root,
            summary_root_level=2,
            summary_exclude_levels=[1],
            include_excluded_ancestors_as_context=True,
        ),
        provider,
    )
    f = idx.files[0]
    nodes = _collect_nodes(f)

    assert len(f.sections) == 2  # raw tree roots A/D preserved
    assert nodes["A"].summary_status == "context_only"
    assert nodes["D"].summary_status == "context_only"
    assert nodes["B"].summary_status == "generated"
    assert nodes["C"].summary_status == "generated"
    assert nodes["E"].summary_status == "generated"
    assert nodes["F"].summary_status == "generated"


def test_summary_view_groups_share_same_level_1_context(tmp_path: Path):
    root = tmp_path
    (root / "demo.md").write_text("# A\nintro\n## B\nb\n## C\nc\n", encoding="utf-8")
    provider = RecordingProvider()
    build_index(
        BuildOptions(
            root=root,
            summary_root_level=2,
            summary_exclude_levels=[1],
            include_excluded_ancestors_as_context=True,
        ),
        provider,
    )
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert "# A" in call["section_text"]
    assert "## B" in call["section_text"]
    assert "## C" in call["section_text"]
    assert set(call["id_to_title"].values()) == {"B", "C"}
    assert "A" not in call["id_to_title"].values()


def test_response_schema_targets_only(tmp_path: Path):
    root = tmp_path
    (root / "demo.md").write_text("# A\n## B\n### C\n", encoding="utf-8")
    provider = RecordingProvider()
    build_index(
        BuildOptions(
            root=root,
            summary_root_level=2,
            summary_exclude_levels=[1],
            include_excluded_ancestors_as_context=True,
        ),
        provider,
    )
    call = provider.calls[0]
    assert set(call["id_to_title"].values()) == {"B", "C"}
