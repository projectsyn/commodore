FROM docker.io/python:3.8.3-slim-buster AS base

WORKDIR /app

ENV HOME=/app \
    PIPENV_VENV_IN_PROJECT=1

RUN pip install pipenv

FROM base AS builder

RUN apt-get update && apt-get install -y \
      build-essential \
      make \
 && rm -rf /var/lib/apt/lists/*

ENV VIRTUALENV_SEEDER=pip

COPY Pipfile Pipfile.lock ./

RUN chown 1001 /app
USER 1001

RUN pipenv install

FROM docker.io/golang:1.14-stretch AS helm_binding_builder

RUN apt-get update && apt-get install -y \
      python3-cffi \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /virtualenv
COPY --from=builder /app/.venv/lib/python3.8/site-packages/kapitan ./kapitan
RUN ./kapitan/inputs/helm/build.sh

FROM base

RUN apt-get update && apt-get install -y \
      git \
      libnss-wrapper \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv/ ./.venv/
COPY --from=helm_binding_builder \
	/virtualenv/kapitan/inputs/helm/libtemplate.so \
	/virtualenv/kapitan/inputs/helm/helm_binding.py \
	./.venv/lib/python3.8/site-packages/kapitan/inputs/helm/

COPY . ./

ARG BINARY_VERSION=unreleased

RUN sed -ie "s/^__version__ = 'Unreleased'$/__version__ = '$BINARY_VERSION'/" ./commodore/__init__.py

RUN chgrp 0 /app/ \
 && chmod g+rwX /app/

USER 1001

ENTRYPOINT [ "/app/tools/entrypoint.sh", "pipenv", "run", "commodore" ]
