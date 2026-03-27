from pathlib import Path

import pytest

from md_scope.exceptions import InvalidRangeError
from md_scope.reader import read_lines


def test_read_lines_with_max_limit(tmp_path: Path):
    f = tmp_path / "x.md"
    f.write_text("1\n2\n3\n4\n5\n", encoding="utf-8")
    payload = read_lines(f, 2, 5, max_lines=2)
    assert payload["returned_start"] == 2
    assert payload["returned_end"] == 3
    assert payload["truncated"] is True
    assert payload["content"] == "2\n3"


def test_read_lines_invalid_range(tmp_path: Path):
    f = tmp_path / "x.md"
    f.write_text("1\n2\n", encoding="utf-8")
    with pytest.raises(InvalidRangeError):
        read_lines(f, 3, 2, max_lines=10)

