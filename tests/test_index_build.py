from pathlib import Path

from md_scope.index_builder import BuildOptions, build_index
from md_scope.summary.providers import provider_from_name


def test_index_build_for_multi_files_and_no_heading(tmp_path: Path):
    root = tmp_path
    (root / "a.md").write_text("# A\nx\n## B\ny\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "b.md").write_text("plain content only\nline2\n", encoding="utf-8")

    idx = build_index(BuildOptions(root=root), provider_from_name("openai-compatible"))
    assert idx.stats.file_count == 2
    assert idx.stats.section_count >= 2

    paths = {f.path for f in idx.files}
    assert "a.md" in paths
    assert "sub/b.md" in paths

    b_file = next(f for f in idx.files if f.path == "sub/b.md")
    assert len(b_file.sections) == 1
    assert b_file.sections[0].title.startswith("Document:")
