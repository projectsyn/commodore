import pytest

from commodore.dependency_mgmt import tools


@pytest.mark.parametrize(
    "components,expected",
    [
        ([], ""),
        (["a"], "'a'"),
        (["a", "b"], "'a' and 'b'"),
        # Verify that Oxford comma is used in lists with >= 2 items
        (
            ["a", "b", "c"],
            "'a', 'b', and 'c'",
        ),
        (
            ["a", "b", "c", "d", "e"],
            "'a', 'b', 'c', 'd', and 'e'",
        ),
    ],
)
def test_format_component_list(components, expected):
    assert tools.format_component_list(components) == expected
