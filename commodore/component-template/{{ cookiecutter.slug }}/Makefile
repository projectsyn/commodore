MAKEFLAGS += --warn-undefined-variables
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := all
.DELETE_ON_ERROR:
.SUFFIXES:

include Makefile.vars.mk

.PHONY: help
help: ## Show this help
	@grep -E -h '\s##\s' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = "(: ).*?## "}; {gsub(/\\:/,":", $$1)}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: all
all: lint

.PHONY: lint
lint: lint_jsonnet lint_yaml lint_adoc ## All-in-one linting

.PHONY: lint_jsonnet
lint_jsonnet: $(JSONNET_FILES) ## Lint jsonnet files
	$(JSONNET_DOCKER) $(JSONNETFMT_ARGS) --test -- $?

.PHONY: lint_yaml
lint_yaml: ## Lint yaml files
	$(YAMLLINT_DOCKER) -f parsable -c $(YAMLLINT_CONFIG) $(YAMLLINT_ARGS) -- .

.PHONY: lint_adoc
lint_adoc: ## Lint documentation
	$(VALE_CMD) $(VALE_ARGS)

.PHONY: format
format: format_jsonnet ## All-in-one formatting

.PHONY: format_jsonnet
format_jsonnet: $(JSONNET_FILES) ## Format jsonnet files
	$(JSONNET_DOCKER) $(JSONNETFMT_ARGS) -- $?

.PHONY: docs-serve
docs-serve: ## Preview the documentation
	$(ANTORA_PREVIEW_CMD)

.PHONY: compile
.compile:
	mkdir -p dependencies
	$(COMMODORE_CMD)

.PHONY: test
test: commodore_args += -f tests/$(instance).yml
test: .compile ## Compile the component

{%- if cookiecutter.add_golden == "y" %}
.PHONY: gen-golden
gen-golden: commodore_args += -f tests/$(instance).yml
gen-golden: .compile ## Update the reference version for target `golden-diff`.
	@rm -rf tests/golden/$(instance)
	@mkdir -p tests/golden/$(instance)
	@cp -R compiled/. tests/golden/$(instance)/.

.PHONY: golden-diff
golden-diff: commodore_args += -f tests/$(instance).yml
golden-diff: .compile ## Diff compile output against the reference version. Review output and run `make gen-golden golden-diff` if this target fails.
	@git diff --exit-code --minimal --no-index -- tests/golden/$(instance) compiled/
{%- endif %}

.PHONY: clean
clean: ## Clean the project
	rm -rf compiled dependencies vendor helmcharts jsonnetfile*.json || true
