"""
Unit-tests for catalog compilation
"""

import click
from unittest.mock import patch
import pytest

from commodore import compile
from commodore.config import Config


def lieutenant_query(api_url, api_token, api_endpoint, api_id):
    if api_endpoint == "clusters":
        return {"id": api_id}

    if api_endpoint == "tenants":
        return {"id": api_id}

    raise click.ClickException(f"call to unexpected API endpoint '#{api_endpoint}'")


@patch("commodore.cluster.lieutenant_query")
def test_no_tenant_reference(test_patch):
    customer_id = "t-wild-fire-234"
    config = Config(
        "https://syn.example.com", "token", "ssh://git@git.example.com", False
    )
    test_patch.side_effect = lieutenant_query
    with pytest.raises(click.ClickException) as err:
        compile.load_cluster_from_api(config, customer_id)
    assert "cluster does not have a tenant reference" in str(err)
