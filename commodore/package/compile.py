from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from textwrap import dedent

import click

from commodore.compile import clean_working_tree
from commodore.cluster import update_target
from commodore.compile import setup_compile_environment
from commodore.config import Config
from commodore.dependency_mgmt import fetch_components
from commodore.helpers import kapitan_compile, relsymlink, yaml_dump
from commodore.inventory import Inventory
from commodore.postprocess import postprocess_components


def compile_package(
    cfg: Config,
    pkg_path_: str,
    root_class: str,
    value_files_: Iterable[str],
):
    # Clean working tree before compiling package, some of our symlinking logic expects
    # that `inventory/` is cleaned before symlinks are created.
    # TODO(sg): Make this conditional on not running local mode for package compilation
    clean_working_tree(cfg)

    pkg_path = Path(pkg_path_).resolve()
    value_files = [Path(f).resolve() for f in value_files_]

    # NOTE(sg): The assumption here is that package repo names generally reflect the
    # package name (possibly with a prefix `package-`). As long as a package only uses
    # relative includes internally, the package name shouldn't matter for compilation.
    pkg_name = pkg_path.stem.replace("package-", "")

    # Verify root class
    root_class_path = root_class.replace(".", "/")
    root_cls = pkg_path / f"{root_class_path}.yml"
    if not root_cls.is_file():
        raise click.ClickException(f"Root class {root_cls} doesn't exist.")

    _setup_inventory(cfg.inventory, pkg_name, root_class, value_files)

    # Symlink package to inventory
    relsymlink(pkg_path, cfg.inventory.package_dir(pkg_name).parent, pkg_name)

    # setup bootstrap target
    update_target(cfg, cfg.inventory.bootstrap_target)

    fetch_components(cfg)

    update_target(cfg, cfg.inventory.bootstrap_target)

    aliases = cfg.get_component_aliases()
    for alias, c in aliases.items():
        update_target(cfg, alias, c)

    inventory, targets = setup_compile_environment(cfg)

    kapitan_compile(
        cfg,
        targets,
        search_paths=[cfg.vendor_dir],
        fetch_dependencies=True,
    )
    postprocess_components(cfg, inventory, cfg.get_components())


def _setup_inventory(
    inv: Inventory, pkg_name: str, root_class: str, value_files: Iterable[Path]
):
    """Setup inventory files which would usually be provided in the cluster's global
    config.
    """
    inv.ensure_dirs()

    tenant_dir = inv.tenant_config_dir("t-fake")
    tenant_dir.mkdir(exist_ok=True)

    # Generate class hierarchy from all additional values files and the target class
    # provided as command line arguments. We use this list as the top-level hierarchy in
    # class `global.commodore`.
    classes = []
    for f in value_files:
        # Add class for value file
        classes.append(f"t-fake.{f.stem}")
        # Symlink value file to inventory
        relsymlink(f, tenant_dir, f.name)

    # Add the package after the additional test config, so that we can provide relevant
    # facts etc. before the package classes are rendered.
    classes.append(f"{pkg_name}.{root_class}")

    # setup global.commodore class with class hierarchy containing package target class
    # to compile and any additional value classes provided on the command line.
    global_commodore = inv.global_config_dir / "commodore.yml"
    global_commodore.parent.mkdir(exist_ok=True)
    yaml_dump(
        {
            "classes": classes,
        },
        global_commodore,
    )
    # TODO(sg): Figure out what else we want to provide fallback values for.
    #  The idea is that packages provide test files to override these values if they
    #  need to.
    yaml_dump(
        {
            "parameters": {
                "cluster": {
                    "catalog_url": "ssh://git@git.example.com/org/repo.git",
                    "name": "c-green-test-1234",
                    "tenant": "t-silent-test-1234",
                },
                "facts": {
                    "distribution": "x-fake-distribution",
                    "cloud": "x-fake-cloud",
                    "region": "x-fake-region",
                },
                "argocd": {
                    "namespace": "syn",
                },
                "kapitan": {
                    "secrets": {
                        "vaultkv": {
                            "VAULT_ADDR": "https://vault.syn.example.com",
                            "VAULT_SKIP_VERIFY": "false",
                            "VAULT_CAPATH": "/etc/ssl/certs/",
                            "auth": "token",
                            "engine": "kv-v2",
                            "mount": "clusters/kv",
                        },
                    },
                },
            }
        },
        inv.params_file,
    )

    # Fake Argo CD lib
    # We plug "fake" Argo CD library here because every component relies on it
    # and we don't want to provide it every time when compiling a single component.
    with open(inv.lib_dir / "argocd.libjsonnet", "w", encoding="utf-8") as argocd_libf:
        argocd_libf.write(
            dedent(
                """
            local ArgoApp(component, namespace, project='', secrets=true) = {};
            local ArgoProject(name) = {};

            {
              App: ArgoApp,
              Project: ArgoProject,
            }"""
            )
        )
