#!/usr/bin/env bash
set -euo pipefail

KIT_URL="https://skillhub-1251783334.cos.ap-guangzhou.myqcloud.com/install/latest.tar.gz"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

curl -fsSL "$KIT_URL" -o "$TMP_DIR/latest.tar.gz"
tar -xzf "$TMP_DIR/latest.tar.gz" -C "$TMP_DIR"

INSTALLER="$TMP_DIR/cli/install.sh"
if [[ ! -f "$INSTALLER" ]]; then
  echo "Error: install.sh not found at $INSTALLER" >&2
  find "$TMP_DIR" -maxdepth 3 -print >&2
  exit 1
fi

bash "$INSTALLER" "$@"
