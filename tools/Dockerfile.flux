# Pushed to docker.io/vshn/flux:v0.0.1

FROM docker.io/fluxcd/flux:1.15.0

RUN /sbin/apk add --no-cache \
    g++ \
    gcc \
    libffi-dev \
    make \
    musl-dev \
    openssl-dev \
    py-pip \
    python3-dev

RUN pip3 install --upgrade kapitan
