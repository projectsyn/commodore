MAKEFLAGS += -j4

ifneq "$(shell which docker 2>/dev/null)" ""
	DOCKER_CMD    ?= $(shell which docker)
	DOCKER_USERNS ?= ""
else
	DOCKER_CMD    ?= podman
	DOCKER_USERNS ?= keep-id
endif
DOCKER_ARGS ?= --rm --tty --user "$$(id -u):$$(id -g)" --userns=$(DOCKER_USERNS)

vale_cmd           ?= $(DOCKER_CMD) run $(DOCKER_ARGS) --volume "$${PWD}"/docs/modules/ROOT/pages:/pages ghcr.io/vshn/vale:2.15.5 --minAlertLevel=error --config=/pages/.vale.ini /pages
antora_preview_cmd ?= $(DOCKER_CMD) run --rm --publish 35729:35729 --publish 2020:2020 --volume "${PWD}/.git":/preview/antora/.git --volume "${PWD}/docs":/preview/antora/docs ghcr.io/vshn/antora-preview:3.1.2.3 --style=syn --antora=docs

UNAME := $(shell uname)
ifeq ($(UNAME), Linux)
	OS = linux-x64
	OPEN = xdg-open
endif
ifeq ($(UNAME), Darwin)
	OS = darwin-x64
	OPEN = open
endif

.PHONY: all
all: docs

.PHONY: docs-serve
docs-serve:
	$(antora_preview_cmd)

.PHONY: docs-vale
docs-vale:
	$(vale_cmd)


###
### Section for Commodore linting and testing
###

include tox.mk

###
### Section for Commodore image build using GitHub actions
###

# Project parameters
BINARY_NAME ?= commodore

GITVERSION ?= $(shell git describe --tags --always --match=v* --dirty=+dirty || (echo "command failed $?"; exit 1))
PYVERSION ?= $(shell git describe --tags --always --match=v* | cut -d- -f1,2 || (echo "command failed $?"; exit 1))

IMAGE_NAME ?= docker.io/projectsyn/$(BINARY_NAME):test

.PHONY: docker

docker:
	$(DOCKER_CMD) build --build-arg PYVERSION=$(PYVERSION) \
		--build-arg GITVERSION=$(GITVERSION) \
		-t $(IMAGE_NAME) .
	@echo built image $(IMAGE_NAME)

.PHONY: inject-version
inject-version:
	@if [ -n "${CI}" ]; then\
		echo "In CI";\
		echo "PYVERSION=${PYVERSION}" >> "${GITHUB_ENV}";\
	else\
		poetry version "${PYVERSION}";\
	fi
	# Always inject Git version
	sed -i "s/^__git_version__.*$$/__git_version__ = '${GITVERSION}'/" commodore/__init__.py

.PHONY: test_integration
test_integration:
	poetry run pytest -m integration -n auto ./tests

.PHONY: test_coverage
test_coverage:
	poetry run pytest -m "not bench" -n auto --cov="commodore" --cov-report lcov

.PHONY: test_gen_golden
test_gen_golden:
	COMMODORE_TESTS_GEN_GOLDEN=true poetry run pytest ./tests/test_catalog.py
