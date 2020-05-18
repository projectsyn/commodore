#!/usr/bin/env bash

set -e

# Make sure that if we are using an arbitrary UID that it appears in /etc/passwd,
# otherwise this will cause issues with things like cloning with git+ssh
# reference: https://access.redhat.com/documentation/en-us/openshift_container_platform/3.11/html/creating_images/creating-images-guidelines#use-uid

export LD_PRELOAD=/usr/lib/libnss_wrapper.so
export NSS_WRAPPER_PASSWD=/tmp/passwd
export NSS_WRAPPER_GROUP=/etc/group

if ! whoami &> /dev/null; then
  echo "commodore:x:$(id -u):0:commodore user:${HOME}:/sbin/nologin" > "${NSS_WRAPPER_PASSWD}"
fi

if [ -z "${SSH_AUTH_SOCK}" ]; then
  eval "$(ssh-agent)"
  ssh-add $(grep -rlE 'BEGIN .+ PRIVATE KEY' /app/.ssh) || echo "No SSH keys were added"
fi

exec "$@"
