.PHONY: lint_flake8 lint_pylint lint_safety lint_bandit lint_readme

TOX_COMMAND = docker run --rm -v $(PWD):/src:ro -v $(PWD)/.tox:/app/.tox docker.io/painless/tox

lint_flake8:
	$(TOX_COMMAND) tox -e flake8

lint_pylint:
	$(TOX_COMMAND) tox -e pylint

lint_safety:
	$(TOX_COMMAND) tox -e safety

lint_bandit:
	$(TOX_COMMAND) tox -e bandit

lint_readme:
	$(TOX_COMMAND) tox -e readme

.PHONY: test_py36 test_py37 test_py38

test_py36:
	$(TOX_COMMAND) tox -e py36

test_py37:
	$(TOX_COMMAND) tox -e py37

test_py38:
	$(TOX_COMMAND) tox -e py38
