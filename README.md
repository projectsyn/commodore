# Project Syn: Commodore

**Please note that this project is in its early stages and under active development**.

See [CHANGELOG.md](/CHANGELOG.md) for changelogs of each release version of
Commodore.

See [DockerHub](https://hub.docker.com/r/projectsyn/commodore) for pre-built
Docker images of Commodore.

## Overview

Commodore provides opinionated tenant-aware management of
[Kapitan](https://kapitan.dev/) inventories and templates. Commodore uses
Kapitan for the heavy lifting of rendering templates and resolving a
hierachical configuration structure.

Commodore introduces the concept of a component, which is a bundle of Kapitan
templates and associated Kapitan classes which describe how to render the
templates. Commodore fetches any components that are required for a given
configuration before running Kapitan, and sets up symlinks so Kapitan can find
the component classes.

Commodore also supports additional processing on the output of Kapitan, such
as patching in the desired namespace for a Helm chart which has been rendered
using `helm template`.

## System Requirements

* Python 3.6+
* [Pipenv](https://github.com/pypa/pipenv)
* Docker

## Getting started

1. Install requirements

   Install pipenv according to the upstream
   [documentation](https://github.com/pypa/pipenv#installation).

   Create the Commdore pip environment:

    ```console
    pipenv install --dev
    ```

    Build the Kapitan helm binding:
    * Linux:

       ```console
       pipenv run build_kapitan_helm_binding
       ```

    * OS X:

      Note: At the moment you'll need a working Go compiler to build the Kapitan Helm
      bindings on OS X.

      ```console
      pipenv run sh -c '${VIRTUAL_ENV}/lib/python3.*/site-packages/kapitan/inputs/helm/build.sh'
      ```

1. Setup a `.env` file to configure Commodore (don't use quotes):

   ```shell
   # URL of Lieutenant API
   COMMODORE_API_URL=https://lieutenant-api.example.com/
   # Lieutenant API token
   COMMODORE_API_TOKEN=<my-token>
   # Base URL for global Git repositories
   COMMODORE_GLOBAL_GIT_BASE=ssh://git@github.com/projectsyn
   # Your local user ID to be used in the container (optional, defaults to root)
   USER_ID=<your-user-id>
   ```

   For Commodore to work, you need to run an instance of the
   [Lieutenant API](https://github.com/projectsyn/lieutenant-api) somewhere
   (locally is fine too).

   Commodore component repositories must exist in
   `${COMMODORE_GLOBAL_GIT_BASE}/commodore_components/` with the repository
   named identically to the component name.

   Note: Commodore currently only supports fetching remote Git repositories
   via SSH.

1. Run Commodore

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

A docker-compose setup enables running Commodore in a container.
The environment variables are picked up from the local `.env` file.
By default your `~/.ssh/` directory is mounted into the container and an `ssh-agent` is started.
You can skip starting an agent by setting the `SSH_AUTH_SOCK` env variable and mounting the socket into the container.

1. Build the Docker image inside of the cloned Commodore repository:

```console
docker-compose build
```

1. Run the built image:

```console
docker-compose run commodore compile $CLUSTER_ID
```

## Documentation

Run the `make docs` command in the `docs` subfolder to generate the Antora documentation website locally. The website will be available at the `_antora/index.html` file.

After writing the documentation, please use the `make check` command and correct any warnings raised by the tool.
