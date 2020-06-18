pages   := $(shell find docs -type f -name '*.adoc')
web_dir := ./_antora

docker_cmd  ?= docker
docker_opts ?= --rm --tty --user "$$(id -u)"

antora_cmd  ?= $(docker_cmd) run $(docker_opts) --volume "$${PWD}":/antora vshn/antora:2.3.0
antora_opts ?= --cache-dir=.cache/antora

vale_cmd ?= $(docker_cmd) run $(docker_opts) --volume "$${PWD}"/docs/modules/ROOT/pages:/pages vshn/vale:2.1.1 --minAlertLevel=error /pages

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

# This will clean the Antora Artifacts, not the npm artifacts
.PHONY: clean
clean:
	rm -rf $(web_dir)

.PHONY: docs
docs:    $(web_dir)/index.html

$(web_dir)/index.html: playbook.yml $(pages)
	$(antora_cmd) $(antora_opts) $<

.PHONY: check
check:
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

BINARY_VERSION = $(shell git describe --tags --always --dirty --match=v* || (echo "command failed $$?"; exit 1))
VERSION ?= $(BINARY_VERSION)

IMAGE_NAME ?= docker.io/vshn/$(BINARY_NAME):$(VERSION)

.PHONY: docker

docker:
	docker build --build-arg BINARY_VERSION=$(BINARY_VERSION) -t $(IMAGE_NAME) .
	@echo built image $(IMAGE_NAME)

COMPONENT_TEST_IMAGE_NAME ?= docker.io/vshn/$(BINARY_NAME)-component-test:$(VERSION)

.PHONY: docker-component-test
docker-component-test:
	docker build -t $(COMPONENT_TEST_IMAGE_NAME) -f tools/Dockerfile.component_test .
	@echo built image $(COMPONENT_TEST_IMAGE_NAME)
