"""
Unit-tests for helpers
"""
import commodore.helpers as helpers


def test_apierror():
    e = helpers.ApiError("test")
    assert f"{e}" == "test"

    try:
        raise helpers.ApiError("test2")
    except helpers.ApiError as e2:
        assert f"{e2}" == "test2"
