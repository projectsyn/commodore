MAKEFLAGS += -j4

docker_cmd  ?= docker
docker_opts ?= --rm --tty --user "$$(id -u)"

vale_cmd ?= $(docker_cmd) run $(docker_opts) --volume "$${PWD}"/docs/modules/ROOT/pages:/pages vshn/vale:2.1.1 --minAlertLevel=error /pages

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

GITVERSION ?= $(shell git describe --tags --always --match=v* --dirty=+dirty || (echo "command failed $?"; exit 1))
PYVERSION ?= $(shell git describe --tags --always --abbrev=0 --match=v* || (echo "command failed $?"; exit 1))

IMAGE_NAME ?= docker.io/vshn/$(BINARY_NAME):test

.PHONY: docker

docker:
	docker build --build-arg PYVERSION=$(PYVERSION) \
		--build-arg GITVERSION=$(GITVERSION) \
		-t $(IMAGE_NAME) .
	@echo built image $(IMAGE_NAME)
