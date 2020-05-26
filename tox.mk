.PHONY: tox lint_flake8 lint_pylint lint_safety lint_bandit lint_readme

TOX_COMMAND = poetry run tox

tox:
	$(TOX_COMMAND)

lint_flake8:
	$(TOX_COMMAND) -e flake8

lint_pylint:
	$(TOX_COMMAND) -e pylint

lint_safety:
	$(TOX_COMMAND) -e safety

lint_bandit:
	$(TOX_COMMAND) -e bandit

lint_readme:
	$(TOX_COMMAND) -e readme

.PHONY: test_py36 test_py37 test_py38

test_py36:
	$(TOX_COMMAND) -e py36

test_py37:
	$(TOX_COMMAND) -e py37

test_py38:
	$(TOX_COMMAND) -e py38
