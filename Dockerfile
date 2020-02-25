FROM docker.io/python:3.8.1-slim-buster AS base

FROM base AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y make build-essential git && apt-get clean
RUN pip install poetry

RUN mkdir -p /app/.config && chown -R 1001 /app
USER 1001
ENV HOME=/app

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.in-project true && \
    poetry install --no-dev

COPY . ./

ARG BINARY_VERSION=v0.0.0+dirty
RUN sed -ie "s/^__version__ = 'v0.0.0+dirty'$/__version__ = '$BINARY_VERSION'/" ./commodore/__init__.py

ARG PYPACKAGE_VERSION=v0.0.0+dirty
RUN poetry version "$PYPACKAGE_VERSION" && poetry build

FROM docker.io/golang:1.13-buster AS helm_binding_builder

RUN apt-get update && apt-get install -y python3-cffi && apt-get clean

WORKDIR /virtualenv
COPY --from=builder /app/.venv/lib/python3.8/site-packages/kapitan ./kapitan
RUN ./kapitan/inputs/helm/build.sh

FROM base

WORKDIR /app
RUN apt-get update && apt-get install -y git libnss-wrapper make build-essential && apt-get clean

COPY --from=builder /app/dist/commodore-*-py3-none-any.whl ./

RUN pip install ./commodore-*-py3-none-any.whl

RUN apt-get purge --purge -y make build-essential && apt-get autoremove -y && rm /app/*.whl

COPY --from=helm_binding_builder \
	/virtualenv/kapitan/inputs/helm/libtemplate.so \
	/virtualenv/kapitan/inputs/helm/helm_binding.py \
	/usr/local/lib/lib/python3.8/site-packages/kapitan/inputs/helm/

RUN ssh-keyscan -t rsa git.vshn.net > /app/.known_hosts

ENV GIT_SSH=/app/tools/ssh

RUN chown 1001 /app
USER 1001

ENTRYPOINT ["/usr/local/bin/commodore"]
