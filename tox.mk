.PHONY: tox lint lint_flake8 lint_pylint lint_bandit

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

lint: lint_flake8 lint_pylint lint_bandit lint_mypy link_black

.PHONY: test_py36 test_py37 test_py38

test_py3.6:
	$(TOX_COMMAND) -e py36

test_py3.7:
	$(TOX_COMMAND) -e py37

test_py3.8:
	$(TOX_COMMAND) -e py38

test_py3.9:
	$(TOX_COMMAND) -e py39
