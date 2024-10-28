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

.PHONY: lintenv_flake8 lintenv_pylint lintenv_bandit lintenv_mypy lintenv_black

lintenv_flake8:
	$(TOX_COMMAND) -e flake8 --notest

lintenv_pylint:
	$(TOX_COMMAND) -e pylint --notest

lintenv_bandit:
	$(TOX_COMMAND) -e bandit --notest

lintenv_mypy:
	$(TOX_COMMAND) -e mypy --notest

lintenv_black:
	$(TOX_COMMAND) -e black --notest

.PHONY: test_py3.10 test_py3.11

test_py3.10:
	$(TOX_COMMAND) -e py310

test_py3.11:
	$(TOX_COMMAND) -e py311

.PHONY: testenv_py3.10 testenv_py3.11

testenv_py3.10:
	$(TOX_COMMAND) -e py310 --notest

testenv_py3.11:
	$(TOX_COMMAND) -e py311 --notest

.PHONY: bench_py3.10 bench_py3.11

bench_py3.10:
	$(TOX_COMMAND) -e py310-bench

bench_py3.11:
	$(TOX_COMMAND) -e py311-bench

.PHONY: benchenv_py3.10 benchenv_py3.11

benchenv_py3.10:
	$(TOX_COMMAND) -e py310-bench --notest

benchenv_py3.11:
	$(TOX_COMMAND) -e py311-bench --notest
