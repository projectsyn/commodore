from unittest import mock

from click.testing import CliRunner
import pytest

from commodore import cli


@pytest.mark.parametrize(
    "args,exitcode,output",
    [
        (
            [],
            1,
            "Error: Can't fetch Lieutenant token. Please provide the Lieutenant API URL.\n",
        ),
        (
            ["--api-url=https://syn.example.com"],
            0,
            "id-1234\n",
        ),
    ],
)
@mock.patch.object(cli, "fetch_token")
def test_commodore_fetch_token(fetch_token, capsys, args, exitcode, output):
    fetch_token.side_effect = lambda cfg: "id-1234"
    runner = CliRunner()

    result = runner.invoke(cli.commodore, ["fetch-token"] + args)

    assert result.exit_code == exitcode
    assert result.stdout == output
