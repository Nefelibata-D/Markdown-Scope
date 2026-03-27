from md_scope.markdown_parser import parse_markdown_sections


def test_heading_hierarchy_and_ranges():
    lines = [
        "# A",
        "text",
        "## B",
        "text",
        "### C",
        "text",
        "## D",
        "text",
    ]
    roots = parse_markdown_sections(lines, "x.md")
    assert len(roots) == 1
    a = roots[0]
    assert a.title == "A"
    assert a.start == 1
    assert a.end == 8
    assert len(a.children) == 2
    b = a.children[0]
    d = a.children[1]
    assert b.title == "B"
    assert b.start == 3
    assert b.end == 6
    assert len(b.children) == 1
    c = b.children[0]
    assert c.title == "C"
    assert c.start == 5
    assert c.end == 6
    assert d.start == 7
    assert d.end == 8


def test_ignore_headings_inside_fenced_code_blocks():
    lines = [
        "# Real",
        "```python",
        "# not-a-heading",
        "## not-a-heading-either",
        "```",
        "## Child",
    ]
    roots = parse_markdown_sections(lines, "x.md")
    assert len(roots) == 1
    real = roots[0]
    assert real.title == "Real"
    assert len(real.children) == 1
    assert real.children[0].title == "Child"


def test_ignore_headings_in_front_matter():
    lines = [
        "---",
        "title: demo",
        "# not-heading",
        "---",
        "# Real",
    ]
    roots = parse_markdown_sections(lines, "x.md")
    assert len(roots) == 1
    assert roots[0].title == "Real"


def test_ignore_headings_in_html_comment_block():
    lines = [
        "# Real",
        "<!--",
        "## not-heading",
        "-->",
        "## Child",
    ]
    roots = parse_markdown_sections(lines, "x.md")
    assert len(roots) == 1
    assert roots[0].title == "Real"
    assert len(roots[0].children) == 1
    assert roots[0].children[0].title == "Child"
