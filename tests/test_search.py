from pathlib import Path

from md_scope.index_builder import BuildOptions, build_index
from md_scope.searcher import search_index
from md_scope.summary.providers import provider_from_name


def test_search_by_title_and_target(tmp_path: Path):
    root = tmp_path
    (root / "SKILL.md").write_text("# Skill\n## Install\nUse uv\n", encoding="utf-8")
    (root / "reference").mkdir()
    (root / "reference" / "a.md").write_text("# Ref\n## Install\nUse pip\n", encoding="utf-8")

    idx = build_index(BuildOptions(root=root), provider_from_name("openai-compatible"))
    all_hits = search_index(idx, "install", field="title")
    assert len(all_hits) == 2

    scoped_hits = search_index(idx, "install", field="title", target="reference")
    assert len(scoped_hits) == 1
    assert scoped_hits[0]["file_name"] == "reference/a.md"
