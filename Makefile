MAKEFLAGS += -j4

docker_cmd  ?= docker
docker_opts ?= --rm --tty --user "$$(id -u)"

vale_cmd           ?= $(docker_cmd) run $(docker_opts) --volume "$${PWD}"/docs/modules/ROOT/pages:/pages vshn/vale:2.6.1 --minAlertLevel=error --config=/pages/.vale.ini /pages
antora_preview_cmd ?= $(docker_cmd) run --rm --publish 35729:35729 --publish 2020:2020 --volume "${PWD}":/preview/antora vshn/antora-preview:2.3.7 --style=syn --antora=docs

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
PYVERSION ?= $(shell git describe --tags --always --abbrev=0 --match=v* || (echo "command failed $?"; exit 1))

IMAGE_NAME ?= docker.io/projectsyn/$(BINARY_NAME):test

.PHONY: docker

docker:
	docker build --build-arg PYVERSION=$(PYVERSION) \
		--build-arg GITVERSION=$(GITVERSION) \
		-t $(IMAGE_NAME) .
	@echo built image $(IMAGE_NAME)

inject-version:
	sed -i "s/^__git_version__.*$$/__git_version__ = '${GITVERSION}'/" commodore/__init__.py
	poetry version "${PYVERSION}"

.PHONY: test_integration
test_integration:
	poetry run pytest -m integration
