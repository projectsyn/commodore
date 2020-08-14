#!/bin/bash

set -euo pipefail

# TODO: nicer pipeline
readonly pyver="python$(python -V 2>&1 | cut -d' ' -f2 | cut -d. -f1-2)"
readonly helm_binding_path="${VIRTUAL_ENV}/lib/${pyver}/site-packages/kapitan/inputs/helm"
readonly helm_dependency_path="${VIRTUAL_ENV}/lib/${pyver}/site-packages/kapitan/dependency_manager/helm"
readonly dockerfile="$(dirname "$0")/Dockerfile.build_kapitan_helm_binding"

docker build --build-arg PY_VER="$pyver" -t kapitan-helm-build -f "${dockerfile}" "$VIRTUAL_ENV"
docker create -ti --name khb kapitan-helm-build:latest bash
docker cp khb:/virtualenv/kapitan/inputs/helm/libtemplate.so "$helm_binding_path"
docker cp khb:/virtualenv/kapitan/dependency_manager/helm/helm_fetch.so "$helm_dependency_path"
docker rm -f khb
"$helm_binding_path"/build.sh
"$helm_dependency_path"/build.sh
