# Changelog

Please document all notable changes to this project in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased]

### Added

* Ability to manage dependencies with jsonnet-bundler ([#190])
* Mypy static type analysis to the tox/CI environments. ([#180])
* Add `--pad-arrays` to component template jsonnetfmt arguments ([#186])
* New `commodore cluster list` command ([#179])
* New `commodore component delete` command ([#188])

### Changed

* Slightly improved error message in case `commodore component new` is called in
  a folder that is not a populated (compiled) catalog ([#183])
* Vault default values ([#176])
* Improved `component new` documentation ([#182])
* `component new` restricts allowed component slugs ([#189])

### Fixed

* Fix failing bandit CI check ([#185])
* Ignore component versions if not included ([#177])
* Fix Jsonnet linting error in component template ([#186])

## [v0.2.3]

### Added

* Validation of component slug ([#153])
* `component compile` now applies postprocessing filters ([#154])
* Option to disable postprocessing filters ([#155])
* `--interactive` option to prompt push confirmation ([#157])
* Extend component template with docs setup ([#158])
* Build Helm bindings for native Helm dependencies ([#161])
* Replaced playbook.yml with custom command ([#165])
* Introduce EditorConfig ([#167])

### Changed

* Reworked documentation ([#147])
* Use Reclass to discover components ([#160])

## [v0.2.2]

### Fixed

* Ignore filename too long ([#151])

## [v0.2.1]

### Fixed

* Read token from file ([#148])

## [v0.2.0]

### Added

* `getValueOrDefault` helper ([#125])
* `makeMergeable` helper ([#126])
* `commodore component compile` to compile a single component ([#122])
* Option to explicitly set a component's display name ([#133])
* labels to issue templates ([#134])
* Vale Makefile target in component template ([#137])
* Allow overriding Git user info for catalog commits ([#140])
* Refactor tests to work with new setup-python ([#143])

### Changed

* `compile` and `clean` commands were moved to the `catalog` command group ([#122])
* `new-component` command was moved to the `component` command group ([#122])
* Jsonnet library file extension to `.libsonnet` in component template ([#137])
* Applied the component template to Commodore itself ([#145])

### Fixed

* Commit messages from automated catalog updates do no longer contain a leading newline ([#136])

## [v0.1.6]

### Changed
* Show some logs only in verbose mode ([#100])
* Use Kapitan Python lib instead of running the binary ([#130])

### Added
* Allow overwriting of component git repo URLs ([#100])
* Introduce trace log level with `-vvv` flag ([#100])
* Helpers for managing HTTP proxy environment variables ([#106])

### Fixed
* Handle empty facts ([#103])

## [v0.1.5]

### Changed
* Dockerfile to support local docker-compose setup ([#99])
* Remove the customer git base fallback and make the value required from the API ([#99])

## [v0.1.4]

### Fixed
* Vault error handling ([#95])
* Optional facts ([#88])

### Changed
* Organize global calsses in folders ([#91])

### Added
* Include lieutenant-instance fact ([#94])

## [v0.1.3]

### Fixed

* Changed all f-strings without interpolations to regular strings ([#81])
* Adjusted Dockerfile so image builds again

### Changed

* Bulk updated dependencies

## [v0.1.2]

### Fixed

* Build process properly sets Commodore binary version ([#58]).

## [v0.1.1]

### Added

* Option to provide API token to Commodore from file instead of directly as
  argument ([#53]).

## [v0.1.0]

Initial implementation

[Unreleased]: https://github.com/projectsyn/commodore/compare/v0.2.3...HEAD
[v0.1.0]: https://github.com/projectsyn/commodore/releases/tag/v0.1.0
[v0.1.1]: https://github.com/projectsyn/commodore/releases/tag/v0.1.1
[v0.1.2]: https://github.com/projectsyn/commodore/releases/tag/v0.1.2
[v0.1.3]: https://github.com/projectsyn/commodore/releases/tag/v0.1.3
[v0.1.4]: https://github.com/projectsyn/commodore/releases/tag/v0.1.4
[v0.1.5]: https://github.com/projectsyn/commodore/releases/tag/v0.1.5
[v0.1.6]: https://github.com/projectsyn/commodore/releases/tag/v0.1.6
[v0.2.0]: https://github.com/projectsyn/commodore/releases/tag/v0.2.0
[v0.2.1]: https://github.com/projectsyn/commodore/releases/tag/v0.2.1
[v0.2.2]: https://github.com/projectsyn/commodore/releases/tag/v0.2.2
[v0.2.3]: https://github.com/projectsyn/commodore/releases/tag/v0.2.3

[#53]: https://github.com/projectsyn/commodore/pull/53
[#58]: https://github.com/projectsyn/commodore/pull/58
[#81]: https://github.com/projectsyn/commodore/pull/81
[#88]: https://github.com/projectsyn/commodore/pull/88
[#91]: https://github.com/projectsyn/commodore/pull/91
[#94]: https://github.com/projectsyn/commodore/pull/94
[#95]: https://github.com/projectsyn/commodore/pull/95
[#99]: https://github.com/projectsyn/commodore/pull/99
[#100]: https://github.com/projectsyn/commodore/pull/100
[#103]: https://github.com/projectsyn/commodore/pull/103
[#106]: https://github.com/projectsyn/commodore/pull/106
[#122]: https://github.com/projectsyn/commodore/pull/122
[#125]: https://github.com/projectsyn/commodore/pull/125
[#126]: https://github.com/projectsyn/commodore/pull/126
[#130]: https://github.com/projectsyn/commodore/pull/130
[#133]: https://github.com/projectsyn/commodore/pull/133
[#134]: https://github.com/projectsyn/commodore/pull/134
[#136]: https://github.com/projectsyn/commodore/issues/136
[#137]: https://github.com/projectsyn/commodore/pull/137
[#140]: https://github.com/projectsyn/commodore/pull/140
[#143]: https://github.com/projectsyn/commodore/pull/143
[#145]: https://github.com/projectsyn/commodore/pull/145
[#147]: https://github.com/projectsyn/commodore/pull/153
[#148]: https://github.com/projectsyn/commodore/pull/148
[#151]: https://github.com/projectsyn/commodore/pull/151
[#153]: https://github.com/projectsyn/commodore/pull/153
[#154]: https://github.com/projectsyn/commodore/pull/154
[#155]: https://github.com/projectsyn/commodore/pull/155
[#157]: https://github.com/projectsyn/commodore/pull/157
[#158]: https://github.com/projectsyn/commodore/pull/158
[#160]: https://github.com/projectsyn/commodore/pull/160
[#161]: https://github.com/projectsyn/commodore/pull/161
[#167]: https://github.com/projectsyn/commodore/pull/167
[#176]: https://github.com/projectsyn/commodore/pull/176
[#177]: https://github.com/projectsyn/commodore/pull/177
[#179]: https://github.com/projectsyn/commodore/pull/179
[#180]: https://github.com/projectsyn/commodore/pull/180
[#182]: https://github.com/projectsyn/commodore/pull/182
[#183]: https://github.com/projectsyn/commodore/pull/183
[#185]: https://github.com/projectsyn/commodore/pull/185
[#186]: https://github.com/projectsyn/commodore/pull/186
[#188]: https://github.com/projectsyn/commodore/pull/188
[#189]: https://github.com/projectsyn/commodore/pull/189
[#190]: https://github.com/projectsyn/commodore/pull/190
