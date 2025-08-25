FROM docker.io/golang:1.25.0 AS golang

FROM docker.io/python:3.12.11-slim-bookworm AS base

ARG TARGETARCH
ENV TARGETARCH=${TARGETARCH:-amd64}

ENV HOME=/app

WORKDIR ${HOME}

FROM base AS builder

ENV PATH=${PATH}:${HOME}/.local/bin:/usr/local/go/bin

ARG POETRY_VERSION=1.8.5
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
      git \
      libffi-dev \
 && rm -rf /var/lib/apt/lists/* \
 && curl -sSL https://install.python-poetry.org | python - --version ${POETRY_VERSION} \
 && mkdir -p /app/.config

COPY --from=golang /usr/local/go /usr/local/go

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
 && poetry install --no-dev --no-root

COPY . ./

ARG PYVERSION=v0.0.0
ARG GITVERSION=v0.0.0+dirty

RUN sed -i "s/^__git_version__.*$/__git_version__ = '${GITVERSION}'/" commodore/__init__.py \
 && poetry version "${PYVERSION}" \
 && poetry build --format wheel

RUN pip install ./dist/syn_commodore-*-py3-none-any.whl

ARG KUSTOMIZE_VERSION=5.7.1
ARG JSONNET_BUNDLER_VERSION=v0.6.3
ARG HELM_VERSION=v3.18.6

RUN commodore tool install helm --version ${HELM_VERSION} \
 && commodore tool install kustomize --version ${KUSTOMIZE_VERSION} \
 && commodore tool install jb --version ${JSONNET_BUNDLER_VERSION}

FROM base AS runtime

ENV PYTHON_MINOR="${PYTHON_VERSION%.*}"

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      git \
      gpg \
      libnss-wrapper \
      openssh-client \
 && rm -rf /var/lib/apt/lists/* \
 && echo "    ControlMaster auto\n    ControlPath /tmp/%r@%h:%p" >> /etc/ssh/ssh_config

COPY --from=builder \
      /usr/local/lib/python${PYTHON_MINOR}/site-packages/ \
      /usr/local/lib/python${PYTHON_MINOR}/site-packages/
COPY --from=builder \
      /usr/local/bin/kapitan* \
      /usr/local/bin/commodore* \
      /usr/local/bin/

COPY --from=builder \
      /app/.cache/commodore/tools/ \
      /app/.cache/commodore/tools/

RUN ln -s \
      /app/.cache/commodore/tools/helm \
      /app/.cache/commodore/tools/jb \
      /app/.cache/commodore/tools/kustomize \
      /usr/local/bin/

COPY ./tools/entrypoint.sh /usr/local/bin/

RUN chgrp -R 0 /app/ \
 && chmod g+rwX /app/ \
 && chmod g+rwX /app/.cache \
 && chmod g+rwX /app/.cache/commodore \
 && mkdir /app/.gnupg \
 && chmod ug+w /app/.gnupg

USER 1001

# OIDC token callback
EXPOSE 18000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh", "commodore"]
