"""Version parsing must keep numeric segments with suffixes."""
import pytest


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("v1.2.3", (1, 2, 3)),
        ("1.2.3-rc1", (1, 2, 3)),
        ("v1.10beta.0", (1, 10, 0)),
        ("1.2", (1, 2, 0)),
    ],
)
def test_parse_version_handles_suffixes(bot_tt, raw, expected):
    assert bot_tt.parse_version(raw) == expected
