#!/bin/bash

set -euo pipefail

readonly command='kapitan refs'

usage() {
    echo "$0 -p <vault_path> -k <key in vault secret> [-r <reference_name>]"
    echo "   -p path/to/secret/in/vault"
    echo "   -k key in vault secret"
    echo "   -r refname [default: vault_path/key]"
}

vault_path=
key=
refname=

echo "$#"
if [[ "$#" -eq 0 ]]; then
    usage
    exit 1
fi

while getopts 'hp:r:k:' opt; do
    case "$opt" in
        h)
            usage
            exit 0
            ;;
        p) vault_path="$OPTARG" ;;
        r) refname="$OPTARG" ;;
        k) key="$OPTARG" ;;
        *)
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "$refname" ]]; then
    refname="$vault_path/$key"
fi

echo -n "$vault_path:$key" | $command --refs-path ./catalog/refs -t cluster -w "vaultkv:${refname}" -f-

# vim: set et sw=4 ts=4 :
