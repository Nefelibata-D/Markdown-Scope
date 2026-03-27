from pathlib import Path

from md_scope.index_builder import BuildOptions, build_index
from md_scope.index_updater import update_index
from md_scope.summary.providers import provider_from_name


def _section_map(index):
    out = {}
    for f in index.files:
        for s in f.sections:
            out[(f.path, s.title)] = s
            for c in s.children:
                out[(f.path, c.title)] = c
    return out


def test_update_reuses_unchanged_section_id_and_summary(tmp_path: Path):
    root = tmp_path
    f = root / "a.md"
    f.write_text("# A\nbody\n## B\nbody b\n", encoding="utf-8")

    old = build_index(BuildOptions(root=root), provider_from_name("openai-compatible"))
    new = update_index(root, old, provider_from_name("openai-compatible"))

    old_map = _section_map(old)
    new_map = _section_map(new)
    assert old_map[("a.md", "A")].id == new_map[("a.md", "A")].id
    assert old_map[("a.md", "A")].summary == new_map[("a.md", "A")].summary
    assert old_map[("a.md", "B")].id == new_map[("a.md", "B")].id


def test_update_regenerates_changed_section(tmp_path: Path):
    root = tmp_path
    f = root / "a.md"
    f.write_text("# A\nbody\n## B\nbody b\n", encoding="utf-8")
    old = build_index(BuildOptions(root=root), provider_from_name("openai-compatible"))

    f.write_text("# A\nbody changed\n## B\nbody b\n", encoding="utf-8")
    new = update_index(root, old, provider_from_name("openai-compatible"))

    old_map = _section_map(old)
    new_map = _section_map(new)
    assert old_map[("a.md", "A")].content_hash != new_map[("a.md", "A")].content_hash
