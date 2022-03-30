import functools
import json
import os

from pathlib import Path
from typing import Dict, Any

from commodore.postprocess.jsonnet import _import_cb, _native_callbacks

import _jsonnet
import requests
import pytest


def tc_files(tc: str) -> (str, Path):
    basedir = Path(__file__).parent
    return basedir / f"{tc}.jsonnet", basedir / f"{tc}.json"


def render_jsonnet(tmp_path: Path, inputf: Path):
    def _inventory() -> Dict[str, Any]:
        return {}

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
    [
        "jsonnet/namespaced",
        "jsonnet/renderArray",
        "jsonnet/generateResources",
    ],
)
def test_jsonnet(tmp_path: Path, tc):
    inputf, expectedf = tc_files(tc)
    os.makedirs(tmp_path / "lib")
    resp = requests.get(
        "https://raw.githubusercontent.com/bitnami-labs/kube-libsonnet/v1.19.0/kube.libsonnet"
    )
    with open(tmp_path / "lib" / "kube.libjsonnet", "w") as f:
        f.write(resp.text)
    result = render_jsonnet(tmp_path, inputf)
    with open(expectedf) as e:
        expected = json.load(e)

    assert result == expected
