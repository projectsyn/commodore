FROM docker.io/python:3.8.6-slim-buster AS base

ENV HOME=/app

WORKDIR ${HOME}

FROM base AS builder

ENV PATH=${PATH}:${HOME}/.poetry/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
 && rm -rf /var/lib/apt/lists/* \
 && curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python - --version 1.1.0 \
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

RUN pip install ./dist/commodore-*-py3-none-any.whl

FROM docker.io/golang:1.16-buster AS helm_binding_builder

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3-cffi \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /virtualenv

COPY --from=builder /usr/local/lib/python3.8/site-packages/kapitan ./kapitan

RUN ./kapitan/inputs/helm/build.sh \
 && ./kapitan/dependency_manager/helm/build.sh

FROM base AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      git \
      libnss-wrapper \
      openssh-client \
 && rm -rf /var/lib/apt/lists/* \
 && echo "    ControlMaster auto\n    ControlPath /tmp/%r@%h:%p" >> /etc/ssh/ssh_config

COPY --from=builder \
      /usr/local/lib/python3.8/site-packages/ /usr/local/lib/python3.8/site-packages/
COPY --from=builder \
      /usr/local/bin/kapitan* \
      /usr/local/bin/commodore* \
      /usr/local/bin/

COPY --from=helm_binding_builder \
      /virtualenv/kapitan/inputs/helm/libtemplate.so \
      /virtualenv/kapitan/inputs/helm/helm_binding.py \
      /usr/local/lib/python3.8/site-packages/kapitan/inputs/helm/

COPY --from=helm_binding_builder \
      /virtualenv/kapitan/dependency_manager/helm/helm_fetch.so \
      /usr/local/lib/python3.8/site-packages/kapitan/dependency_manager/helm/

RUN curl -sLo /usr/local/bin/jb \
  https://github.com/jsonnet-bundler/jsonnet-bundler/releases/download/v0.4.0/jb-linux-amd64 \
  && chmod +x /usr/local/bin/jb

COPY ./tools/entrypoint.sh /usr/local/bin/

RUN chgrp 0 /app/ \
 && chmod g+rwX /app/

USER 1001

ENTRYPOINT ["/usr/local/bin/entrypoint.sh", "commodore"]
