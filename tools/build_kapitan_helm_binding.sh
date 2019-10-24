#!/bin/bash

set -euo pipefail

readonly helm_binding_path="${VIRTUAL_ENV}/lib/python3.6/site-packages/kapitan/inputs/helm"
readonly dockerfile="$(dirname "$0")/Dockerfile.build_kapitan_helm_binding"

docker build -t kapitan-helm-build -f "${dockerfile}" "$VIRTUAL_ENV"
docker create -ti --name khb kapitan-helm-build:latest bash
docker cp khb:/virtualenv/kapitan/inputs/helm/libtemplate.so "$helm_binding_path"
docker rm -f khb
"$helm_binding_path"/build.sh
