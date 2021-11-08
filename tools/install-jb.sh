#!/bin/bash
set -eu

VERSION=${1:-}

if [ "x${VERSION}" = "x" ]; then
	echo "Usage: $0 VERSION"
	exit 3
fi

ARCH=$(uname -m)
case $ARCH in
	armv7*) ARCH="arm";;
	aarch64|arm64) ARCH="arm64";;
	x86_64|amd64) ARCH="amd64";;
	*)
		echo "Unsupported arch: $ARCH"
		exit 5
	::
esac

curl -fsSLo /usr/local/bin/jb \
	"https://github.com/jsonnet-bundler/jsonnet-bundler/releases/download/$VERSION/jb-linux-$ARCH"

chmod +x /usr/local/bin/jb
