import click
import pytest
import yaml

from commodore.config import Config
from commodore.inventory import lint


@pytest.fixture
def config(tmp_path):
    """
    Setup test config object
    """
    return Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )


def test_check_removed_reclass_variables_error(tmp_path, config):
    testf = tmp_path / "test.yml"
    with open(testf, "w") as f:
        yaml.safe_dump({"parameters": {"test": "${customer:name}"}}, f)

    with pytest.raises(click.ClickException) as e:
        lint.check_removed_reclass_variables(config, "tests", [testf])

    assert "Found 1 usages of removed reclass variables in the tests." in str(e.value)
