import json
from pathlib import Path

from commodore.component import Component
from commodore.config import Config

from commodore.dependency_mgmt import jsonnet_bundler


def test_write_jsonnetfile(config: Config, tmp_path: Path):
    config.register_component(Component("test-component", work_dir=tmp_path))
    config.register_component(Component("test-component-2", work_dir=tmp_path))
    dirs = [
        "dependencies/test-component",
        "dependencies/test-component-2",
        "dependencies/lib",
    ]

    file = tmp_path / "jsonnetfile.json"

    jsonnet_bundler.write_jsonnetfile(
        file, jsonnet_bundler.jsonnet_dependencies(config)
    )

    with open(file) as jf:
        jf_string = jf.read()
        assert jf_string[-1] == "\n"
        jf_contents = json.loads(jf_string)
        assert jf_contents["version"] == 1
        assert jf_contents["legacyImports"]
        deps = jf_contents["dependencies"]
        for dep in deps:
            assert dep["source"]["local"]["directory"] in dirs


def test_inject_essential_libraries(tmp_path: Path):
    file = tmp_path / "jsonnetfile.json"
    jsonnet_bundler.write_jsonnetfile(file, [])

    jsonnet_bundler.inject_essential_libraries(file)

    with open(file) as jf:
        jf_string = jf.read()
        assert jf_string[-1] == "\n"
        jf_contents = json.loads(jf_string)
        assert jf_contents["version"] == 1
        assert jf_contents["legacyImports"]
        deps = jf_contents["dependencies"]
        assert len(deps) == 1
        assert (
            deps[0]["source"]["git"]["remote"]
            == "https://github.com/bitnami-labs/kube-libsonnet"
        )
        assert deps[0]["version"] == "v1.19.0"


def test_clear_jsonnet_lock_file(tmp_path: Path):
    jsonnetfile = tmp_path / "jsonnetfile.json"
    jsonnet_lock = tmp_path / "jsonnetfile.lock.json"
    with open(jsonnetfile, "w") as jf:
        json.dump(
            {
                "version": 1,
                "dependencies": [
                    {
                        "source": {
                            "git": {
                                "remote": "https://github.com/brancz/kubernetes-grafana.git",
                                "subdir": "grafana",
                            }
                        },
                        "version": "master",
                    }
                ],
                "legacyImports": True,
            },
            jf,
        )
    with open(jsonnet_lock, "w") as jl:
        json.dump(
            {
                "version": 1,
                "dependencies": [
                    {
                        "source": {
                            "git": {
                                "remote": "https://github.com/brancz/kubernetes-grafana.git",
                                "subdir": "grafana",
                            }
                        },
                        "version": "57b4365eacda291b82e0d55ba7eec573a8198dda",
                        "sum": "92DWADwGjnCfpZaL7Q07C0GZayxBziGla/O03qWea34=",
                    }
                ],
                "legacyImports": True,
            },
            jl,
        )
    jsonnet_bundler.fetch_jsonnet_libraries(tmp_path)

    assert jsonnet_lock.is_file()
    with open(jsonnet_lock, "r") as file:
        data = json.load(file)
        assert (
            data["dependencies"][0]["version"]
            != "57b4365eacda291b82e0d55ba7eec573a8198dda"
        )
