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

.PHONY: test_py3.7 test_py3.8 test_py3.9

test_py3.7:
	$(TOX_COMMAND) -e py37

test_py3.8:
	$(TOX_COMMAND) -e py38

test_py3.9:
	$(TOX_COMMAND) -e py39

.PHONY: testenv_py3.7 testenv_py3.8 testenv_py3.9

testenv_py3.7:
	$(TOX_COMMAND) -e py37 --notest

testenv_py3.8:
	$(TOX_COMMAND) -e py38 --notest

testenv_py3.9:
	$(TOX_COMMAND) -e py39 --notest

.PHONY: bench_py3.7 bench_py3.8 bench_py3.9

bench_py3.7:
	$(TOX_COMMAND) -e py37-bench

bench_py3.8:
	$(TOX_COMMAND) -e py38-bench

bench_py3.9:
	$(TOX_COMMAND) -e py39-bench

.PHONY: benchenv_py3.7 benchenv_py3.8 benchenv_py3.9

benchenv_py3.7:
	$(TOX_COMMAND) -e py37-bench --notest

benchenv_py3.8:
	$(TOX_COMMAND) -e py38-bench --notest

benchenv_py3.9:
	$(TOX_COMMAND) -e py39-bench --notest
