#!/bin/bash

set -euo pipefail

readonly command='kapitan refs'

usage() {
    echo "$0 -p <vault_path> [-r <reference_name>]"
    echo "   -p / --vault-path path/to/secret/in/vault"
    echo "   -r / --commodore-ref refname [default: vault-path]"
}

vault_path=
refname=

echo "$#"
if [[ "$#" -eq 0 ]]; then
    usage
    exit 1
fi

while getopts 'hp:r:' opt; do
    case "$opt" in
        h)
            usage
            exit 0
            ;;
        p) vault_path="$OPTARG" ;;
        r) refname="$OPTARG" ;;
        *)
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "$refname" ]]; then
    refname="$vault_path"
fi

echo -n "$vault_path" | $command --refs-path ./catalog/refs -t cluster -w "vaultkv:${refname}" -f-

# vim: set et sw=4 ts=4 :
