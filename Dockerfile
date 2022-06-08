FROM docker.io/python:3.10.5-slim-bullseye AS base

ENV HOME=/app

WORKDIR ${HOME}

FROM base AS builder

ENV PATH=${PATH}:${HOME}/.poetry/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
      libffi-dev \
 && rm -rf /var/lib/apt/lists/* \
 && curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python - --version 1.1.13 \
 && mkdir -p /app/.config

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

RUN ./tools/install-jb.sh v0.4.0

FROM base AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      git \
      libnss-wrapper \
      openssh-client \
 && rm -rf /var/lib/apt/lists/* \
 && echo "    ControlMaster auto\n    ControlPath /tmp/%r@%h:%p" >> /etc/ssh/ssh_config

COPY --from=builder \
      /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
COPY --from=builder \
      /usr/local/bin/kapitan* \
      /usr/local/bin/commodore* \
      /usr/local/bin/helm* \
      /usr/local/bin/jb \
      /usr/local/bin/

RUN ln -s /usr/local/bin/helm3 /usr/local/bin/helm

COPY ./tools/entrypoint.sh /usr/local/bin/

RUN chgrp 0 /app/ \
 && chmod g+rwX /app/

USER 1001

# OIDC token callback
EXPOSE 18000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh", "commodore"]
