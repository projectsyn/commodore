.PHONY: tox lint lint_flake8 lint_pylint lint_bandit lint_black

TOX_COMMAND = poetry run tox

tox:
	$(TOX_COMMAND)

lint_flake8:
	$(TOX_COMMAND) -e flake8

lint_pylint:
	$(TOX_COMMAND) -e pylint

lint_bandit:
	$(TOX_COMMAND) -e bandit

lint_mypy:
	$(TOX_COMMAND) -e mypy

lint_black:
	$(TOX_COMMAND) -e black

lint: lint_flake8 lint_pylint lint_bandit lint_mypy lint_black

.PHONY: test_py3.7 test_py3.8 test_py3.9

test_py3.7:
	$(TOX_COMMAND) -e py37

test_py3.8:
	$(TOX_COMMAND) -e py38

test_py3.9:
	$(TOX_COMMAND) -e py39

.PHONY: bench_py3.7 bench_py3.8 bench_py3.9

bench_py3.7:
	$(TOX_COMMAND) -e py37-bench

bench_py3.8:
	$(TOX_COMMAND) -e py38-bench

bench_py3.9:
	$(TOX_COMMAND) -e py39-bench
