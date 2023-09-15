#!/bin/bash

set -eo pipefail

KAPITAN_DIRECTORY=$1
echo "Patching Kapitan in $KAPITAN_DIRECTORY"
if [ -f ${KAPITAN_DIRECTORY}/.patched ]; then
  echo "Already patched"
  exit 0
fi

curl -L https://raw.githubusercontent.com/projectsyn/reclass-rs/main/hack/kapitan_0.32_reclass_rs.patch | patch -p1 -d $KAPITAN_DIRECTORY
touch ${KAPITAN_DIRECTORY}/.patched
