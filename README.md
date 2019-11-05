# Commodore: Build dynamic inventories and compile catalogs with Kapitan

## System Requirements

* Python 3.6 (important because of Pipenv)
* [Pipenv](https://github.com/pypa/pipenv)
* Docker

## Getting started


1. Install requirements

   ```console
   pipenv install
   pipenv run build_kapitan_helm_binding
   ```

1. Setup a `.env` file to configure Commodore (or provide command line flags):

   ```shell
   # URL of SYNventory API
   COMMODORE_API_URL="https://synventory.syn.vshn.net/"
   # Base URL (local or remote) for global Git repositories
   COMMODORE_GLOBAL_GIT_BASE="ssh://git@git.vshn.net/syn/"
   # Base URL (local or remote) for customer Git repositories
   COMMODORE_CUSTOMER_GIT_BASE="ssh://git@git.vshn.net/syn/customers/"
   ```

   Note: currently Commodore only supports fetching Git repositories via SSH

1. Run commodore

   ```console
   pipenv run commodore
   ```

1. Start hacking on Commodore
