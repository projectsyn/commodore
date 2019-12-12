#!/bin/bash

if [ -z "$VAULT_USERNAME" ]; then
	read -r -p "Vault username (<customer>-<cluster>): " VAULT_USERNAME
	export VAULT_USERNAME
fi
if [ -z "$VAULT_PASSWORD" ]; then
	read -r -s -p "Vault password: " VAULT_PASSWORD
	export VAULT_PASSWORD
fi

kapitan refs --reveal --refs-path catalog/refs -f catalog/manifests
