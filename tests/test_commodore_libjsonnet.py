import functools
import json
import os

from pathlib import Path
from typing import Dict, Any

from commodore.postprocess.jsonnet import _import_cb, _native_callbacks

import _jsonnet
import requests
import pytest
import yaml


TESTS_DIR = Path(__file__).parent / "jsonnet"


def discover_tc():
    files = {
        f.stem
        for f in TESTS_DIR.iterdir()
        if f.is_file() and not f.name.startswith(".")
    }
    print(files)
    return list(files)


def tc_files(tc: str) -> (str, Path):
    return (
        TESTS_DIR / f"{tc}.jsonnet",
        TESTS_DIR / f"{tc}.yaml",
        TESTS_DIR / f"{tc}.json",
    )


def render_jsonnet(tmp_path: Path, inputf: Path, invf: Path):
    inv = {}
    if invf.is_file():
        with open(invf) as invf:
            inv = yaml.safe_load(invf)

    def _inventory() -> Dict[str, Any]:
        return inv

    _native_cb = _native_callbacks
    _native_cb["inventory"] = ((), _inventory)

    resstr = _jsonnet.evaluate_file(
        str(inputf),
        import_callback=functools.partial(_import_cb, tmp_path),
        native_callbacks=_native_cb,
    )
    return json.loads(resstr)


@pytest.mark.parametrize(
    "tc",
    discover_tc(),
)
def test_jsonnet(tmp_path: Path, tc):
    inputf, invf, expectedf = tc_files(tc)
    os.makedirs(tmp_path / "lib")
    resp = requests.get(
        "https://raw.githubusercontent.com/bitnami-labs/kube-libsonnet/v1.19.0/kube.libsonnet"
    )
    with open(tmp_path / "lib" / "kube.libjsonnet", "w") as f:
        f.write(resp.text)
    result = render_jsonnet(tmp_path, inputf, invf)
    with open(expectedf) as e:
        expected = json.load(e)

    assert result == expected
