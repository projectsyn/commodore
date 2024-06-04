"""
Tests for component new command
"""

from __future__ import annotations

import json
import os

import click
import pytest
import shutil
import yaml
from pathlib import Path as P
from subprocess import call
from git import Repo
from datetime import date
from typing import Optional

from conftest import RunnerFunc
from test_component import setup_directory

from commodore.component import template
from commodore.config import Config


def call_component_new(
    tmp_path: P,
    cli_runner: RunnerFunc,
    component_name="test-component",
    lib="--no-lib",
    pp="--no-pp",
    golden="--no-golden-tests",
    matrix="--no-matrix-tests",
    output_dir="",
    extra_args: list[str] = [],
):
    args = ["-d", str(tmp_path), "component", "new"]
    if output_dir:
        args.extend(["--output-dir", str(output_dir)])
    args.extend([component_name, lib, pp, golden, matrix])
    args.extend(extra_args)
    result = cli_runner(args)
    assert result.exit_code == 0
    return result


def _validate_rendered_component(
    tmp_path: P,
    component_name: str,
    has_lib: bool,
    has_pp: bool,
    has_golden: bool,
    has_matrix: bool,
    test_cases: list[str] = ["defaults"],
):
    expected_files = [
        P("README.md"),
        P("renovate.json"),
        P("class", f"{component_name}.yml"),
        P("component", "main.jsonnet"),
        P("component", "app.jsonnet"),
        P("docs", "modules", "ROOT", "pages", "references", "parameters.adoc"),
        P("docs", "modules", "ROOT", "pages", "index.adoc"),
        P(".github", "changelog-configuration.json"),
        P(".github", "PULL_REQUEST_TEMPLATE.md"),
        P(".github", "workflows", "release.yaml"),
        P(".github", "workflows", "test.yaml"),
        P(".github", "ISSUE_TEMPLATE", "01_bug_report.md"),
        P(".github", "ISSUE_TEMPLATE", "02_feature_request.md"),
        P(".github", "ISSUE_TEMPLATE", "config.yml"),
        P(".cruft.json"),
    ]
    for tc in test_cases:
        expected_files.append(P("tests", f"{tc}.yml"))
    if has_lib:
        expected_files.append(P("lib", f"{component_name}.libsonnet"))
    if has_golden:
        for tc in test_cases:
            expected_files.append(
                P(
                    "tests",
                    "golden",
                    tc,
                    component_name,
                    "apps",
                    f"{component_name}.yaml",
                )
            )
    for file in expected_files:
        assert (tmp_path / "dependencies" / component_name / file).exists()
    # Check that we created a worktree
    assert (tmp_path / "dependencies" / component_name / ".git").is_file()
    # Verify that worktree and bare copy configs are correct
    repo = Repo(tmp_path / "dependencies" / component_name)
    assert not repo.bare
    assert P(repo.working_tree_dir) == tmp_path / "dependencies" / component_name
    md_repo = Repo(P(repo.common_dir).resolve())
    assert md_repo.bare
    assert md_repo.working_tree_dir is None
    # Check that there are no uncommitted files in the component repo
    repo = Repo(tmp_path / "dependencies" / component_name)
    assert not repo.is_dirty()
    assert not repo.untracked_files
    # Verify component class
    with open(
        tmp_path / "dependencies" / component_name / "class" / f"{component_name}.yml"
    ) as cclass:
        class_contents = yaml.safe_load(cclass)
        assert "parameters" in class_contents
        params = class_contents["parameters"]
        assert "kapitan" in params
        if has_pp:
            assert "commodore" in params
            assert "postprocess" in params["commodore"]
            assert "filters" in params["commodore"]["postprocess"]
            assert isinstance(params["commodore"]["postprocess"]["filters"], list)

    with open(
        tmp_path
        / "dependencies"
        / component_name
        / ".github"
        / "workflows"
        / "test.yaml"
    ) as ght:
        ghtest = yaml.safe_load(ght)
        assert ghtest["env"] == {"COMPONENT_NAME": component_name}
        assert ("strategy" in ghtest["jobs"]["test"]) == has_matrix
        run_step = ghtest["jobs"]["test"]["steps"][1]
        if has_matrix:
            assert run_step["run"] == "make test -e instance=${{ matrix.instance }}"
        else:
            assert run_step["run"] == "make test"

        if has_golden:
            assert "golden" in ghtest["jobs"]
            assert ("strategy" in ghtest["jobs"]["golden"]) == has_matrix
            run_step = ghtest["jobs"]["golden"]["steps"][1]
            if has_matrix:
                assert (
                    run_step["run"]
                    == "make golden-diff -e instance=${{ matrix.instance }}"
                )
            else:
                assert run_step["run"] == "make golden-diff"

    with open(tmp_path / "dependencies" / component_name / ".cruft.json") as cruftjson:
        cruft_config = json.load(cruftjson)
        expected_keys = {"template", "commit", "checkout", "context", "directory"}
        assert set(cruft_config.keys()) == expected_keys
        assert "cookiecutter" in cruft_config["context"]

        cookiecutter_context = cruft_config["context"]["cookiecutter"]

        context_keys = {
            "name",
            "slug",
            "parameter_key",
            "test_cases",
            "add_lib",
            "add_pp",
            "add_golden",
            "add_matrix",
            "add_go_unit",
            "copyright_holder",
            "copyright_year",
            "github_owner",
            "github_name",
            "github_url",
            "_template",
        }

        assert len(context_keys - set(cookiecutter_context.keys())) == 0

        assert cookiecutter_context["add_matrix"] == "y" if has_matrix else "n"
        assert cookiecutter_context["name"] == component_name
        assert cookiecutter_context["add_golden"] == "y" if has_golden else "n"
        assert cookiecutter_context["test_cases"] == " ".join(test_cases)

    with open(
        tmp_path / "dependencies" / component_name / "renovate.json"
    ) as renovatejson:
        renovateconfig = json.load(renovatejson)
        assert ("postUpgradeTasks" in renovateconfig) == has_golden
        if has_golden:
            assert len(renovateconfig["postUpgradeTasks"]["commands"]) == 1
            cmd = renovateconfig["postUpgradeTasks"]["commands"][0]
            expected_cmd = "make gen-golden-all" if has_matrix else "make gen-golden"
            assert cmd == expected_cmd


def _format_test_case_args(flag: str, test_cases: list[str]) -> list[str]:
    args = []
    for tc in test_cases:
        args.extend([flag, tc])
    return args


@pytest.mark.parametrize("lib", ["--no-lib", "--lib"])
@pytest.mark.parametrize(
    "pp",
    ["--no-pp", "--pp"],
)
@pytest.mark.parametrize(
    "golden",
    ["--no-golden-tests", "--golden-tests"],
)
@pytest.mark.parametrize(
    "matrix",
    ["--no-matrix-tests", "--matrix-tests"],
)
def test_run_component_new_command(
    tmp_path: P, cli_runner: RunnerFunc, lib: str, pp: str, golden: str, matrix: str
):
    """
    Run the component new command
    """
    has_lib = lib == "--lib"
    has_pp = pp == "--pp"
    has_golden = golden == "--golden-tests"
    has_matrix = matrix == "--matrix-tests"

    component_name = "test-component"
    call_component_new(
        tmp_path,
        cli_runner,
        component_name=component_name,
        lib=lib,
        pp=pp,
        golden=golden,
        matrix=matrix,
    )

    _validate_rendered_component(
        tmp_path, component_name, has_lib, has_pp, has_golden, has_matrix
    )


@pytest.mark.parametrize(
    "test_cases",
    [
        [],
        ["foo"],
        ["foo", "bar"],
    ],
)
def test_run_component_new_with_additional_test_cases(
    tmp_path: P, cli_runner: RunnerFunc, test_cases: list[str]
):
    component_name = "test-component"
    tc_args = _format_test_case_args("--additional-test-case", test_cases)
    result = call_component_new(
        tmp_path,
        cli_runner,
        component_name=component_name,
        golden="--golden-tests",
        matrix="--matrix-tests",
        extra_args=tc_args,
    )

    assert (
        " > Forcing matrix tests when multiple test cases requested"
        not in result.stdout
    )
    _validate_rendered_component(
        tmp_path, component_name, False, False, True, True, ["defaults"] + test_cases
    )


def test_run_component_new_force_matrix_additional_test_cases(
    tmp_path: P, cli_runner: RunnerFunc
):
    component_name = "test-component"
    tc_args = ["--additional-test-case", "foo"]
    result = call_component_new(
        tmp_path,
        cli_runner,
        component_name=component_name,
        golden="--golden-tests",
        matrix="--no-matrix-tests",
        extra_args=tc_args,
    )

    assert " > Forcing matrix tests when multiple test cases requested" in result.stdout
    _validate_rendered_component(
        tmp_path, component_name, False, False, True, True, ["defaults", "foo"]
    )


def test_run_component_new_command_with_output_dir(tmp_path: P, cli_runner: RunnerFunc):
    """Verify that rendered component is put into specified output directory.

    This test doesn't validate the contents of the rendered files, that part is covered
    in `test_run_component_new_command()`."""
    component_name = "test-component"
    call_component_new(
        tmp_path,
        cli_runner,
        component_name=component_name,
        output_dir=str(tmp_path),
    )

    assert (tmp_path / component_name).is_dir()
    assert not (tmp_path / "dependencies").exists()


def test_run_component_new_command_with_name(tmp_path: P):
    """
    Run the component new command with the slug option set
    """

    setup_directory(tmp_path)

    component_name = "Component with custom name"
    component_slug = "named-component"
    readme_path = tmp_path / "dependencies" / component_slug / "README.md"
    cruftjson_path = tmp_path / "dependencies" / component_slug / ".cruft.json"

    exit_status = call(
        f"commodore -d {tmp_path} -vvv component new --name '{component_name}' {component_slug}",
        shell=True,
    )

    assert exit_status == 0
    assert os.path.exists(readme_path)

    with open(readme_path, "r") as file:
        lines = file.read().split("\n")
        assert lines[0] == f"# Commodore Component: {component_name}"
        assert any(f"https://hub.syn.tools/{component_slug}" in line for line in lines)

    with open(cruftjson_path, "r") as file:
        cruftjson = json.load(file)
        assert cruftjson["context"]["cookiecutter"]["name"] == component_name


@pytest.mark.parametrize(
    "test_input",
    [
        "component-test-illegal",
        "test-illegal-",
        "-test-illegal",
        "00-test-illegal",
        "TestIllegal",
        "test_illegal",
    ],
)
def test_run_component_new_command_with_illegal_slug(tmp_path: P, test_input):
    """
    Run the component new command with an illegal slug
    """
    setup_directory(tmp_path)
    exit_status = call(
        f"commodore -d {tmp_path} -vvv component new {test_input}", shell=True
    )
    assert exit_status != 0


def test_run_component_new_then_delete(tmp_path: P, cli_runner: RunnerFunc):
    """
    Create a new component, then immediately delete it.
    """
    setup_directory(tmp_path)

    component_name = "test-component"
    result = cli_runner(
        ["-d", tmp_path, "-vvv", "component", "new", component_name, "--lib", "--pp"]
    )
    assert result.exit_code == 0

    result = cli_runner(
        ["-d", tmp_path, "-vvv", "component", "delete", "--force", component_name]
    )
    assert result.exit_code == 0

    # Ensure the dependencies folder is gone.
    assert not (tmp_path / "dependencies" / component_name).exists()

    # Links in the inventory should be gone too.
    for f in [
        tmp_path / "inventory" / "classes" / "components" / f"{component_name}.yml",
        tmp_path / "inventory" / "classes" / "defaults" / f"{component_name}.yml",
        tmp_path / "dependencies" / "lib" / f"{component_name}.libsonnet",
        tmp_path / "vendor" / component_name,
    ]:
        assert not f.exists()

    assert not (tmp_path / "inventory" / "targets" / f"{component_name}.yml").exists()


def test_deleting_inexistant_component(tmp_path: P):
    """
    Trying to delete a component that does not exist results in a non-0 exit
    code.
    """
    setup_directory(tmp_path)
    component_name = "i-dont-exist"

    exit_status = call(
        f"commodore -d {tmp_path} -vvv component delete --force {component_name}",
        shell=True,
    )
    assert exit_status == 2


def test_check_golden_diff(tmp_path: P):
    """
    Verify that `make golden-diff` passes for a component which has golden tests enabled
    """
    setup_directory(tmp_path)

    component_name = "test-component"
    exit_status = call(
        f"commodore -d {tmp_path} -vvv component new {component_name}",
        shell=True,
    )
    assert exit_status == 0

    # Override component Makefile COMMODORE_CMD to use the local Commodore binary
    env = os.environ
    env["COMMODORE_CMD"] = "commodore"

    # Call `make golden-diff` in component directory
    exit_status = call(
        "make golden-diff",
        env=env,
        shell=True,
        cwd=tmp_path / "dependencies" / component_name,
    )
    assert exit_status == 0


@pytest.mark.parametrize(
    "new_args,update_args",
    [
        ([], ["--lib"]),
        ([], ["--pp"]),
        ([], ["--golden-tests"]),
        ([], ["--matrix-tests"]),
        (["--matrix-tests"], ["--no-matrix-tests"]),
        ([], ["--golden-tests", "--matrix-tests"]),
    ],
)
def test_component_update_bool_flags(
    tmp_path: P, cli_runner: RunnerFunc, new_args: list[str], update_args: list[str]
):
    component_name = "test-component"
    new_cmd = [
        "-d",
        str(tmp_path),
        "component",
        "new",
        "--no-lib",
        "--no-pp",
        "--no-golden-tests",
        "--no-matrix-tests",
        component_name,
    ]

    has_lib = "--lib" in new_args
    has_pp = "--pp" in new_args
    has_golden = "--golden-tests" in new_args
    has_matrix = "--matrix-tests" in new_args

    result = cli_runner(new_cmd + new_args)
    assert result.exit_code == 0

    _validate_rendered_component(
        tmp_path, component_name, has_lib, has_pp, has_golden, has_matrix
    )

    update_cmd = [
        "-d",
        str(tmp_path),
        "component",
        "update",
        f"{tmp_path}/dependencies/{component_name}",
    ]
    has_lib = "--lib" in update_args
    has_pp = "--pp" in update_args
    has_golden = "--golden-tests" in update_args
    has_matrix = "--matrix-tests" in update_args

    result = cli_runner(update_cmd + update_args)
    assert result.exit_code == 0

    _validate_rendered_component(
        tmp_path, component_name, has_lib, has_pp, has_golden, has_matrix
    )


def test_component_update_copyright(tmp_path: P, cli_runner: RunnerFunc):
    year = date.today().year
    component_name = "test-component"
    call_component_new(tmp_path, cli_runner, component_name)

    component_path = tmp_path / "dependencies" / component_name
    license_file = component_path / "LICENSE"
    with open(license_file, "r", encoding="utf-8") as lic:
        lines = lic.readlines()
        assert lines[0] == f"Copyright {year}, VSHN AG <info@vshn.ch>\n"

    result = cli_runner(
        [
            "component",
            "update",
            str(component_path),
            "--copyright",
            "Foo Bar Inc. <foobar@example.com>",
        ]
    )
    assert result.exit_code == 0

    with open(license_file, "r", encoding="utf-8") as lic:
        lines = lic.readlines()
        assert lines[0] == f"Copyright {year}, Foo Bar Inc. <foobar@example.com>\n"


@pytest.mark.parametrize("commit", [True, False])
def test_component_update_copyright_year(
    tmp_path: P, cli_runner: RunnerFunc, commit: bool
):
    component_name = "test-component"
    call_component_new(tmp_path, cli_runner, component_name)

    component_path = tmp_path / "dependencies" / component_name
    license_file = component_path / "LICENSE"
    with open(license_file, "r", encoding="utf-8") as lic:
        lines = lic.readlines()
        lines[0] = "Copyright 2019, VSHN AG <info@vshn.ch>\n"

    with open(license_file, "w", encoding="utf-8") as lic:
        lic.writelines(lines)

    cruftjson_file = component_path / ".cruft.json"
    with open(cruftjson_file, "r", encoding="utf-8") as f:
        cruftjson = json.load(f)
        cruftjson["context"]["cookiecutter"]["copyright_year"] = "2019"

    with open(cruftjson_file, "w", encoding="utf-8") as f:
        json.dump(cruftjson, f, indent=2)

    r = Repo(component_path)
    r.index.add(["LICENSE", ".cruft.json"])
    lic_update_commit = r.index.commit("License year")

    commit_arg = ["--commit" if commit else "--no-commit"]

    result = cli_runner(
        ["component", "update", str(component_path), "--update-copyright-year"]
        + commit_arg
    )
    assert result.exit_code == 0

    with open(license_file, "r", encoding="utf-8") as lic:
        lines = lic.readlines()
        year = date.today().year
        assert lines[0] == f"Copyright {year}, VSHN AG <info@vshn.ch>\n"

    assert r.is_dirty() != commit
    if not commit:
        assert r.head.commit == lic_update_commit
    else:
        assert r.head.commit.message.startswith("Update from template\n\n")


def test_component_update_no_cruft_json(tmp_path: P, cli_runner: RunnerFunc):
    component_name = "test-component"
    call_component_new(tmp_path, cli_runner, component_name)

    component_path = tmp_path / "dependencies" / component_name
    cruftjson_file = component_path / ".cruft.json"
    cruftjson_file.unlink()

    result = cli_runner(["component", "update", str(component_path)])
    assert result.exit_code == 1
    assert (
        result.stdout
        == "Error: Provided component path doesn't have `.cruft.json`, can't update.\n"
    )


@pytest.mark.parametrize(
    "initial_cases,additional_cases,removed_cases",
    [
        ([], [], []),
        ([], [], ["defaults"]),
        ([], ["foo"], []),
        ([], ["foo"], ["defaults"]),
        (["foo"], ["bar"], ["foo"]),
        (["foo", "bar"], ["baz"], ["foo", "bar"]),
    ],
)
def test_component_update_test_cases(
    tmp_path: P,
    cli_runner: RunnerFunc,
    initial_cases: list[str],
    additional_cases: list[str],
    removed_cases: list[str],
):
    component_name = "test-component"
    new_args = _format_test_case_args("--additional-test-case", initial_cases)
    call_component_new(
        tmp_path,
        cli_runner,
        component_name,
        golden="--golden-tests",
        matrix="--matrix-tests",
        extra_args=new_args,
    )

    component_path = tmp_path / "dependencies" / component_name

    orig_cases = ["defaults"] + initial_cases

    _validate_rendered_component(
        tmp_path, component_name, False, False, True, True, orig_cases
    )

    update_args = _format_test_case_args("--additional-test-case", additional_cases)
    update_args += _format_test_case_args("--remove-test-case", removed_cases)

    result = cli_runner(["component", "update", str(component_path)] + update_args)

    updated_cases = []
    for tc in orig_cases + additional_cases:
        if tc not in updated_cases and tc not in removed_cases:
            updated_cases.append(tc)

    assert result.exit_code == (0 if len(updated_cases) > 0 else 1)
    if len(updated_cases) == 0:
        assert (
            result.stdout
            == "Error: Component template doesn't support removing all test cases.\n"
        )
        final_cases = orig_cases
    else:
        final_cases = updated_cases

    _validate_rendered_component(
        tmp_path, component_name, False, False, True, True, final_cases
    )


def test_cookiecutter_args_fallback(
    tmp_path: P, cli_runner: RunnerFunc, config: Config
):
    component_name = "test-component"
    call_component_new(tmp_path, cli_runner, component_name)

    component_path = tmp_path / "dependencies" / component_name
    cruft_json_file = component_path / ".cruft.json"

    with open(cruft_json_file, "r", encoding="utf-8") as f:
        cruft_json = json.load(f)

    cruft_json["context"]["cookiecutter"]["foo"] = "bar"
    cruft_json["context"]["cookiecutter"]["baz"] = "qux"

    with open(cruft_json_file, "w", encoding="utf-8") as f:
        json.dump(cruft_json, f, indent=2)

    t = template.ComponentTemplater.from_existing(config, component_path)

    # Verify provided values override values from `.cruft.json`
    assert t.cookiecutter_args["add_golden"] == "n"
    t.golden_tests = True
    assert t.cookiecutter_args["add_golden"] == "y"

    templater_cookiecutter_args = t.cookiecutter_args

    # Verify unknown values from `.cruft.json` are preserved
    assert "foo" in templater_cookiecutter_args
    assert templater_cookiecutter_args["foo"] == "bar"
    assert "baz" in templater_cookiecutter_args
    assert templater_cookiecutter_args["baz"] == "qux"


def test_cookiecutter_args_no_cruft_json(tmp_path: P, config: Config):
    t = template.ComponentTemplater(
        config, "https://git.example.com", None, "test-component"
    )
    t.golden_tests = True
    t.library = False
    t.matrix_tests = False
    t.post_process = False
    t.copyright_holder = ""
    t.github_owner = "projectsyn"
    t.automerge_patch = True
    t.automerge_patch_v0 = False

    templater_cookiecutter_args = t.cookiecutter_args

    assert templater_cookiecutter_args["add_lib"] == "n"
    assert templater_cookiecutter_args["add_golden"] == "y"


def _setup_component_wo_cookiecutter_arg(
    tmp_path: P, cli_runner: RunnerFunc, component_name: str, arg_key: str
):
    call_component_new(tmp_path, cli_runner, component_name, lib="--lib", pp="--pp")
    component_path = tmp_path / "dependencies" / component_name

    with open(component_path / ".cruft.json", "r", encoding="utf-8") as f:
        cruft_json_data = json.load(f)
        del cruft_json_data["context"]["cookiecutter"][arg_key]

    with open(component_path / ".cruft.json", "w", encoding="utf-8") as f:
        json.dump(cruft_json_data, f, indent=2)

    return component_path


@pytest.mark.parametrize("expected", [True, False])
def test_component_templater_updates_cookiecutter_args(
    capsys, tmp_path: P, cli_runner: RunnerFunc, config: Config, expected: bool
):
    component_name = "test-component"
    component_path = _setup_component_wo_cookiecutter_arg(
        tmp_path, cli_runner, component_name, "add_lib"
    )
    if not expected:
        shutil.rmtree(component_path / "lib")

    r = Repo(component_path)
    r.index.add(["*", ".cruft.json"])
    c = r.index.commit("Update from test")

    t = template.ComponentTemplater.from_existing(config, component_path)

    assert t.library == expected

    add_lib = "y" if expected else "n"
    with open(component_path / ".cruft.json", "r", encoding="utf-8") as f:
        cruft_json_data = json.load(f)
        assert cruft_json_data["context"]["cookiecutter"]["add_lib"] == add_lib

    assert r.head.commit != c
    assert r.head.commit.message == "Add missing cookiecutter args to `.cruft.json`"

    captured = capsys.readouterr()
    assert captured.out == " > Adding missing cookiecutter args to `.cruft.json`\n"


@pytest.mark.parametrize("expected", [True, False])
def test_component_templater_has_pp(
    tmp_path: P, cli_runner: RunnerFunc, config: Config, expected: bool
):
    component_name = "test-component"
    component_path = _setup_component_wo_cookiecutter_arg(
        tmp_path, cli_runner, component_name, "add_pp"
    )

    if not expected:
        with open(
            component_path / "class" / f"{component_name}.yml", "r", encoding="utf-8"
        ) as f:
            class_data = yaml.safe_load(f)
            del class_data["parameters"]["commodore"]["postprocess"]

        with open(
            component_path / "class" / f"{component_name}.yml", "w", encoding="utf-8"
        ) as f:
            yaml.safe_dump(class_data, f)

    t = template.ComponentTemplater.from_existing(config, component_path)

    assert t.post_process == expected

    add_pp = "y" if expected else "n"
    with open(component_path / ".cruft.json", "r", encoding="utf-8") as f:
        cruft_json_data = json.load(f)
        assert cruft_json_data["context"]["cookiecutter"]["add_pp"] == add_pp


def test_component_update_raises_on_merge_conflict(
    tmp_path: P, cli_runner: RunnerFunc, config: Config
):
    component_name = "test-component"
    component_path = tmp_path / "dependencies" / component_name
    call_component_new(tmp_path, cli_runner, component_name, lib="--lib")
    with open(component_path / ".cruft.json", "r", encoding="utf-8") as f:
        cruft_json = json.load(f)
    cruft_json["context"]["cookiecutter"]["add_lib"] = "n"
    with open(component_path / ".cruft.json", "w", encoding="utf-8") as f:
        json.dump(cruft_json, f, indent=2)
        f.write("\n")

    with open(
        component_path / "lib" / "test-component.libsonnet", "w", encoding="utf-8"
    ) as f:
        f.write(
            """// Test contents

{
  Foo: {bar: 1, baz: false},
}
"""
        )

    r = Repo(component_path)
    r.index.add([".cruft.json", "lib/test-component.libsonnet"])
    r.index.commit("Update component lib")

    result = cli_runner(["component", "update", "--lib", str(component_path)])

    assert result.exit_code == 1
    stdout_lines = result.stdout.strip().split("\n")
    assert (
        stdout_lines[-1]
        == "Error: Can't commit template changes: merge error in "
        + "'lib/test-component.libsonnet'. Please resolve conflicts and commit manually."
    )


@pytest.mark.parametrize("ignore_template_commit", [True, False])
def test_component_update_ignore_template_commit_id(
    tmp_path: P, cli_runner: RunnerFunc, config: Config, ignore_template_commit: bool
):
    component_name = "test-component"
    component_path = tmp_path / "dependencies" / component_name
    call_component_new(tmp_path, cli_runner, component_name)
    with open(component_path / ".cruft.json", "r", encoding="utf-8") as f:
        cruft_json = json.load(f)
    template_repo = Repo.clone_from(
        "https://github.com/projectsyn/commodore-component-template",
        tmp_path / "template",
    )
    cruft_json["commit"] = template_repo.head.commit.parents[0].hexsha
    with open(component_path / ".cruft.json", "w", encoding="utf-8") as f:
        json.dump(cruft_json, f, indent=2)
        f.write("\n")

    r = Repo(component_path)
    r.index.add([".cruft.json"])
    head = r.index.commit("Update .cruft.json")

    t = template.ComponentTemplater.from_existing(config, component_path)

    changed = t.update(ignore_template_commit=ignore_template_commit)

    assert changed == (not ignore_template_commit)
    assert (r.head.commit == head) == ignore_template_commit
    assert r.is_dirty() == ignore_template_commit


@pytest.mark.parametrize(
    "files,expected,committed",
    [
        ([], 0, []),
        (["foo.txt"], 0, ["foo.txt"]),
        (["foo.txt", "foo.txt.rej"], 1, ["foo.txt"]),
        (["foo.txt", "foo.txt.orig"], 1, ["foo.txt"]),
        (["foo.txt", "foo.txt.rej", "foo.txt.orig"], 2, ["foo.txt"]),
    ],
)
def test_component_diff_commit_ignore_orig_rej_files(
    tmp_path: P,
    cli_runner: RunnerFunc,
    config: Config,
    files: list[str],
    expected: int,
    committed: list[str],
):
    component_name = "test-component"
    component_path = tmp_path / "dependencies" / component_name
    call_component_new(tmp_path, cli_runner, component_name)
    for f in files:
        (component_path / f).touch()

    t = template.ComponentTemplater.from_existing(config, component_path)
    r = Repo(component_path)

    diff, changed = t.diff()

    # Assumption: when we provide files, we always provide one file which gets committed
    assert changed == (len(files) > 0)
    if len(files) == 0:
        assert diff == ""
    else:
        difflines = diff.split("\n")
        assert len(difflines) == len(committed)
        for f in committed:
            assert click.style(f"Added file {f}", fg="green") in difflines

    t.commit("Update")

    assert not r.is_dirty()
    assert len(r.untracked_files) == expected
    assert set(r.untracked_files) == set(
        f for f in files if f.endswith("rej") or f.endswith("orig")
    )


@pytest.mark.parametrize(
    "license_data,expected_holder,expected_year",
    [
        (None, "VSHN AG <info@vshn.ch>", ""),
        ({}, "VSHN AG <info@vshn.ch>", "2021"),
        (
            {"holder": "Foo Inc. <foo@example.com>"},
            "Foo Inc. <foo@example.com>",
            "2021",
        ),
        ({"year": 2022}, "VSHN AG <info@vshn.ch>", "2022"),
        (
            {"holder": "Foo Inc. <foo@example.com>", "year": 2022},
            "Foo Inc. <foo@example.com>",
            "2022",
        ),
    ],
)
def test_component_templater_read_from_modulesync_config(
    tmp_path: P,
    cli_runner: RunnerFunc,
    config: Config,
    license_data: Optional[dict],
    expected_holder: str,
    expected_year: str,
):
    component_name = "test-component"
    call_component_new(tmp_path, cli_runner, component_name)
    component_path = tmp_path / "dependencies" / component_name
    r = Repo(component_path)

    with open(component_path / ".cruft.json", "r", encoding="utf-8") as f:
        cruft_json = json.load(f)

    del cruft_json["context"]["cookiecutter"]["copyright_year"]
    del cruft_json["context"]["cookiecutter"]["copyright_holder"]

    with open(component_path / ".cruft.json", "w", encoding="utf-8") as f:
        json.dump(cruft_json, f, indent=2)
        f.write("\n")
    r.index.add([".cruft.json"])

    if license_data is None and (component_path / ".sync.yml").is_file():
        # Remove existing `.sync.yml`, if necessary
        (component_path / ".sync.yml").unlink(missing_ok=True)
        r.index.remove([".sync.yml"])
    elif license_data is not None:
        # Create `.sync.yml` with provided LICENSE data
        sync_yml = {}
        if len(license_data) > 0:
            sync_yml["LICENSE"] = license_data
        with open(component_path / ".sync.yml", "w", encoding="utf-8") as f:
            yaml.safe_dump(sync_yml, f)
        r.index.add([".sync.yml"])

    r.index.commit("Update component template metadata")

    if not expected_year:
        expected_year = str(date.today().year)

    t = template.ComponentTemplater.from_existing(config, component_path)

    assert t.cookiecutter_args["copyright_holder"] == expected_holder
    assert t.cookiecutter_args["copyright_year"] == expected_year
