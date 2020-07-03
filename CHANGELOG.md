# Changelog

Please document all notable changes to this project in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased]
### Added

* `getValueOrDefault` helper ([#125])
* `makeMergeable` helper ([#126])
* `commodore component compile` to compile a single component ([#122])
* labels to issue templates ([#134])

### Changed

* `compile` and `clean` commands were moved to the `catalog` command group ([#122])
* `new-component` command was moved to the `component` command group ([#122])

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

[Unreleased]: https://github.com/projectsyn/commodore/compare/v0.1.6...HEAD
[v0.1.0]: https://github.com/projectsyn/commodore/releases/tag/v0.1.0
[v0.1.1]: https://github.com/projectsyn/commodore/releases/tag/v0.1.1
[v0.1.2]: https://github.com/projectsyn/commodore/releases/tag/v0.1.2
[v0.1.3]: https://github.com/projectsyn/commodore/releases/tag/v0.1.3
[v0.1.4]: https://github.com/projectsyn/commodore/releases/tag/v0.1.4
[v0.1.5]: https://github.com/projectsyn/commodore/releases/tag/v0.1.5
[v0.1.6]: https://github.com/projectsyn/commodore/releases/tag/v0.1.6
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
[#134]: https://github.com/projectsyn/commodore/pull/134
