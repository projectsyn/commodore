# Commodore: Build dynamic inventories and compile catalogs with Kapitan

## System Requirements

* Python 3.6 (important because of Pipenv)
* [Pipenv](https://github.com/pypa/pipenv)
* Docker

## Getting started

1. Install requirements

   ```console
   pipenv install --dev
   pipenv run build_kapitan_helm_binding
   ```

1. Setup a `.env` file to configure Commodore (or provide command line flags):

   ```shell
   # URL of SYNventory API
   COMMODORE_API_URL="https://synventory.syn.vshn.net/"
   # Base URL (local or remote) for global Git repositories
   COMMODORE_GLOBAL_GIT_BASE="ssh://git@git.vshn.net/syn/"
   # Base URL (local or remote) for customer Git repositories
   COMMODORE_CUSTOMER_GIT_BASE="ssh://git@git.vshn.net/syn/customers/"
   ```

   Note: currently Commodore only supports fetching Git repositories via SSH

1. Run commodore

   ```console
   pipenv run commodore
   ```

1. Start hacking on Commodore

   ```console
   pipenv shell
   ```

   - Write a line of test code, make the test fail
   - Write a line of application code, make the test pass
   - Repeat

1. Run linting and tests

   Auto format with autopep8
   ```console
   pipenv run autopep
   ```

   List all Tox targets:
   ```console
   pipenv run test tox -lv
   ```

   Run all linting and tests:
   ```console
   pipenv run test tox
   ```

   Run just a specific target:
   ```console
   pipenv run test tox -e py38
   ```

   Upgrade dependencies (Pipfile.lock, requirements.txt)
   ```console
   pipenv run test tox -e requirements
   ```

## Run Commodore in Docker

1. Build the Docker image inside of the cloned Commodore repository:

```console
docker build -t commodore .
```

1. Run the built image:

```console
docker run -it --rm \
    -e COMMODORE_API_URL="https://synventory.syn.vshn.net/" \
    -e COMMODORE_GLOBAL_GIT_BASE="ssh://git@git.vshn.net/syn/" \
    -e COMMODORE_CUSTOMER_GIT_BASE="ssh://git@git.vshn.net/syn/customers/" \
    -e SSH_PRIVATE_KEY="$(cat ~/.ssh/id_ed25519)" \
    -v $(pwd)/catalog:/app/catalog/ \
    -v $(pwd)/dependencies:/app/dependencies/ \
    -v $(pwd)/inventory:/app/inventory/ \
    --entrypoint bash \
    commodore
```

1. Set up ssh-agent in the running Docker container for the access to Git repositories:

```console
tools/ssh
eval $(ssh-agent)
ssh-add .identityfile
```

1. Run Commodore inside of the running Docker container:

```console
pipenv run commodore
```
