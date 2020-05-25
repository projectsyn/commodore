FROM docker.io/python:3.8.3-slim-buster AS base

ENV HOME=/app

WORKDIR ${HOME}

FROM base AS builder

RUN apt-get update && apt-get install -y \
      build-essential \
 && rm -rf /var/lib/apt/lists/* \
 && pip install poetry \
 && mkdir -p /app/.config

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.in-project true \
 && poetry install --no-dev

COPY . ./

ARG BINARY_VERSION=v0.0.0+dirty
ARG PYPACKAGE_VERSION=v0.0.0+dirty

RUN sed -ie "s/^__version__ = 'Unreleased'$/__version__ = '$BINARY_VERSION'/" ./commodore/__init__.py \
 && poetry version "$PYPACKAGE_VERSION" \
 && poetry build --format wheel

FROM docker.io/golang:1.14-buster AS helm_binding_builder

RUN apt-get update && apt-get install -y \
      python3-cffi \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /virtualenv

COPY --from=builder /app/.venv/lib/python3.8/site-packages/kapitan ./kapitan

RUN ./kapitan/inputs/helm/build.sh

FROM base AS runtime

RUN apt-get update && apt-get install -y \
      build-essential \
      git \
      libnss-wrapper \
 && rm -rf /var/lib/apt/lists/*

COPY --from=helm_binding_builder \
	/virtualenv/kapitan/inputs/helm/libtemplate.so \
	/virtualenv/kapitan/inputs/helm/helm_binding.py \
	/usr/local/lib/lib/python3.8/site-packages/kapitan/inputs/helm/

COPY --from=builder /app/dist/commodore-*-py3-none-any.whl ./

RUN pip install ./commodore-*-py3-none-any.whl

RUN chgrp 0 /app/ \
 && chmod g+rwX /app/

USER 1001

ENTRYPOINT ["/usr/local/bin/commodore"]
