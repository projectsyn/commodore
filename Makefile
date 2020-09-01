MAKEFLAGS += -j4

pages   := $(shell find docs -type f -name '*.adoc')

docker_cmd  ?= docker
docker_opts ?= --rm --tty --user "$$(id -u)"

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
