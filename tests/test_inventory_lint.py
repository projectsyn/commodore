import click
import pytest
import yaml

from commodore.config import Config
from commodore.inventory import lint


def test_check_removed_reclass_variables_error(tmp_path, config: Config):
    testf = tmp_path / "test.yml"
    with open(testf, "w") as f:
        yaml.safe_dump({"parameters": {"test": "${customer:name}"}}, f)

    with pytest.raises(click.ClickException) as e:
        lint.check_removed_reclass_variables(config, "tests", [testf])

    assert "Found 1 usages of removed reclass variables in the tests." in str(e.value)
