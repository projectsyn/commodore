"""
Unit-tests for catalog compilation
"""

import click
from unittest.mock import patch
import pytest

from commodore import compile
from commodore.config import Config


@patch('commodore.compile.lieutenant_query')
def test_no_customer_repo(test_patch):
    customer_id = "t-wild-fire-234"
    config = Config("https://syn.example.com", "token", "ssh://git@git.example.com", False)
    test_patch.return_value = {
        'id': customer_id
    }
    with pytest.raises(click.ClickException) as excinfo:
        compile._fetch_customer_config(config, customer_id)
    assert customer_id in str(excinfo)
