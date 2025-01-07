from __future__ import annotations

from pathlib import Path

import click

from commodore.config import Config
from commodore.dependency_mgmt.discovery import (
    RESERVED_PACKAGE_PATTERN,
    TENANT_PREFIX_PATTERN,
)
from commodore.dependency_templater import Templater
from commodore.package import package_dependency_dir


class PackageTemplater(Templater):
    @classmethod
    def from_existing(cls, config: Config, path: Path):
        return cls._base_from_existing(config, path, "package")

    def _validate_slug(self, value: str):
        # First perform default slug checks
        slug = super()._validate_slug(value)
        # Then perform additional checks for package slug
        if RESERVED_PACKAGE_PATTERN.match(slug):
            raise click.ClickException(f"Package can't use reserved slug '{slug}'")
        if TENANT_PREFIX_PATTERN.match(slug):
            raise click.ClickException(
                "Package slug can't use reserved tenant prefix 't-'"
            )
        return slug

    @property
    def deptype(self) -> str:
        return "package"

    def dependency_dir(self) -> Path:
        return package_dependency_dir(self.config.work_dir, self.slug)
