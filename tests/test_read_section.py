from pathlib import Path

from md_scope.index_builder import BuildOptions, build_index
from md_scope.reader import read_section
from md_scope.summary.providers import provider_from_name


def test_read_section_returns_subtree_content(tmp_path: Path):
    root = tmp_path
    (root / "doc.md").write_text(
        "# Root\nintro\n## Child\nchild body\n### Leaf\nleaf body\n## Sibling\nsib body\n",
        encoding="utf-8",
    )
    idx = build_index(BuildOptions(root=root), provider_from_name("openai-compatible"))
    file_idx = next(f for f in idx.files if f.path == "doc.md")
    root_id = file_idx.sections[0].id

    payload = read_section(idx, root, root_id, max_lines=100)
    assert payload["title"] == "Root"
    assert payload["truncated"] is False
    assert payload["file_name"] == "doc.md"
    assert "## Child" in payload["content"]
    assert "### Leaf" in payload["content"]
    assert "## Sibling" in payload["content"]
