# Changelog

Please document all notable changes to this project in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased]

### Added

* Generate a best-effort SSH-based push URL for component repos ([#281])

## [v0.4.2] - 2021-01-14

### Added
* Support for rendering component `jsonnetfile.json` from Jsonnet ([#275])

### Fixed
* Correctly handle component instances in Kapitan reference management ([#272])

### Changed
* Component template to ignore `vendor/` from linting ([#276])

## [v0.4.1] 2020-12-28

### Added
* Add GitHub action to build Kapitan docker image from `tools/Dockerfile.kapitan` ([#266])

### Changed
* Always create targets from component aliases ([#269])
* Update dependencies ([#200])

### Fixed
* Correctly create a local branch when overriding component version ([#262])
* Field read when determine revision of the tenant config repository ([#263])
* Remove usage of deprecated `::set-env` in GitHub actions ([#265])

## [v0.4.0] 2020—11—05

### Added

* Add support for component instantiation ([#234]).
* Add basic renovate config to component template ([#249]).
* Ability to configure the working directory ([#230])
* Ability to configure working dir with an environment variable ([#256])

### Changed

* Git repository URLs are now retrieved from the Lieutenant API ([#226])
* Create a Kapitan target for each component ([#227])

  This requires a refactored hierarchy which replaces class includes of
  components with entries in `applications`.
  `classes: [ "components.argocd" ]` becomes `applications: [ "argocd" ]`.
* Pull essential libraries with Jsonnet Bundler ([#246])
* Add option to define postprocessing filters in the Kapitan inventory ([#222]).
* Update component template to use inventory postprocessing filters ([#249]).
* Components are no longer deleted when compiling a cluster ([#253])
  Missing components will be cloned.
  Existing components will be updated.
  This also affects artefacts downloaded by components.
  Component authors must ensure their downloaded path changes with versions.
  Checkout the [component style guide](https://syn.tools/syn/references/style-guide.html#_component_style) for further details.

### Fixed

* Replace remaining references to `common.yml` with `commodore.yml` ([#204])
* Adjust component new/delete to update `jsonnetfile.json` ([#211])
* Provide `inventory_path` in Kapitan's argument cache ([#212])
* Clear Jsonnet lock file ([#215])
* Also make arrays mergeable with `makeMergeable` helper ([#217])

### Removed

* Check for "Old-style" components ([#237])
* Configuration of the global git base ([#247])
  All components must be listed in `commodore.yml` within the global configuration repository.
  The URL of the global configuration repository must be set at Lieutenant on the Tenant object.

## [v0.3.0] - 2020-10-01

### Added

* Ability to manage dependencies with jsonnet-bundler ([#190])
* Mypy static type analysis to the tox/CI environments. ([#180])
* Add `--pad-arrays` to component template jsonnetfmt arguments ([#186])
* New `commodore cluster list` command ([#179])
* New `commodore component delete` command ([#188])

### Changed

* Inventory hierarchy is now dynamic ([#195])

  A class hierarchy needs to be added.
  Check the documentation for details.

* Pass through facts from Lieutenant API to `parameters.facts` ([#192])
* Slightly improved error message in case `commodore component new` is called in
  a folder that is not a populated (compiled) catalog ([#183])
* Vault default values ([#176])
* Improved `component new` documentation ([#182])
* `component new` restricts allowed component slugs ([#189])

### Deprecated

* The following parameters will be removed in a future release.
  They are replaced with corresponding values within `parameters.facts` ([#192]).
  * `parameters.cluster.dist` → `parameters.facts.distribution`
  * `parameters.cloud.provider` → `parameters.facts.cloud`
  * `parameters.cloud.region` → `parameters.facts.region`
  * `parameters.customer.name` → `parameters.cluster.tenant`

### Fixed

* Fix failing bandit CI check ([#185])
* Ignore component versions if not included ([#177])
* Fix Jsonnet linting error in component template ([#186])
* Commit `.editorconfig` in initial commit for component repo ([#201])

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

[Unreleased]: https://github.com/projectsyn/commodore/compare/v0.4.2...HEAD
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
[v0.3.0]: https://github.com/projectsyn/commodore/releases/tag/v0.3.0
[v0.4.0]: https://github.com/projectsyn/commodore/releases/tag/v0.4.0
[v0.4.1]: https://github.com/projectsyn/commodore/releases/tag/v0.4.1
[v0.4.2]: https://github.com/projectsyn/commodore/releases/tag/v0.4.2

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
[#192]: https://github.com/projectsyn/commodore/pull/192
[#195]: https://github.com/projectsyn/commodore/pull/195
[#200]: https://github.com/projectsyn/commodore/pull/200
[#201]: https://github.com/projectsyn/commodore/pull/201
[#204]: https://github.com/projectsyn/commodore/pull/204
[#211]: https://github.com/projectsyn/commodore/pull/211
[#212]: https://github.com/projectsyn/commodore/pull/212
[#215]: https://github.com/projectsyn/commodore/pull/215
[#217]: https://github.com/projectsyn/commodore/pull/217
[#222]: https://github.com/projectsyn/commodore/pull/222
[#226]: https://github.com/projectsyn/commodore/pull/226
[#227]: https://github.com/projectsyn/commodore/pull/227
[#230]: https://github.com/projectsyn/commodore/pull/230
[#234]: https://github.com/projectsyn/commodore/pull/234
[#237]: https://github.com/projectsyn/commodore/pull/237
[#246]: https://github.com/projectsyn/commodore/pull/246
[#247]: https://github.com/projectsyn/commodore/pull/247
[#249]: https://github.com/projectsyn/commodore/pull/249
[#253]: https://github.com/projectsyn/commodore/pull/253
[#256]: https://github.com/projectsyn/commodore/pull/256
[#262]: https://github.com/projectsyn/commodore/pull/262
[#263]: https://github.com/projectsyn/commodore/pull/263
[#265]: https://github.com/projectsyn/commodore/pull/265
[#266]: https://github.com/projectsyn/commodore/pull/266
[#269]: https://github.com/projectsyn/commodore/pull/269
[#272]: https://github.com/projectsyn/commodore/pull/272
[#275]: https://github.com/projectsyn/commodore/pull/275
[#276]: https://github.com/projectsyn/commodore/pull/276
[#281]: https://github.com/projectsyn/commodore/pull/281
