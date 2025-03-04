FROM docker.io/python:3.12.9-slim-bookworm AS base

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
      libffi-dev \
 && rm -rf /var/lib/apt/lists/* \
 && curl -sSL https://install.python-poetry.org | python - --version ${POETRY_VERSION} \
 && mkdir -p /app/.config


ARG GO_VERSION=1.24.1
RUN curl -fsSL -o go.tar.gz https://go.dev/dl/go${GO_VERSION}.linux-${TARGETARCH}.tar.gz \
 && tar -C /usr/local -xzf go.tar.gz \
 && rm go.tar.gz \
 && go version

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

RUN curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 \
 && chmod 700 get_helm.sh \
 && ./get_helm.sh \
 && mv /usr/local/bin/helm /usr/local/bin/helm3 \
 && curl -LO https://git.io/get_helm.sh \
 && chmod 700 get_helm.sh \
 && ./get_helm.sh \
 && mv /usr/local/bin/helm /usr/local/bin/helm2

ARG KUSTOMIZE_VERSION=5.6.0
ARG JSONNET_BUNDLER_VERSION=v0.6.3

RUN ./tools/install-jb.sh ${JSONNET_BUNDLER_VERSION} \
 && curl -fsSLO "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" \
 && chmod +x install_kustomize.sh \
 && ./install_kustomize.sh ${KUSTOMIZE_VERSION} /usr/local/bin

FROM base AS runtime

ENV PYTHON_MINOR="${PYTHON_VERSION%.*}"

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      git \
      gpg \
      libmagic1 \
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
      /usr/local/bin/helm* \
      /usr/local/bin/jb \
      /usr/local/bin/kustomize \
      /usr/local/bin/

RUN ln -s /usr/local/bin/helm3 /usr/local/bin/helm

COPY ./tools/entrypoint.sh /usr/local/bin/

RUN chgrp 0 /app/ \
 && chmod g+rwX /app/ \
 && mkdir /app/.gnupg \
 && chmod ug+w /app/.gnupg

USER 1001

# OIDC token callback
EXPOSE 18000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh", "commodore"]
