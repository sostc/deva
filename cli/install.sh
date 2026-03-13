#!/usr/bin/env bash
set -euo pipefail

MODE="all"
RESTART_GATEWAY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cli-only)
      MODE="cli"
      shift
      ;;
    --plugin-only)
      MODE="plugin"
      shift
      ;;
    --restart-gateway)
      RESTART_GATEWAY=1
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: install.sh [--cli-only|--plugin-only] [--restart-gateway]

Installs the skillhub CLI and/or skillhub plugin for OpenClaw.
USAGE
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Supports two archive layouts:
# 1) install.sh at kit root: ./install.sh + ./cli + ./plugin
# 2) install.sh inside cli folder: ./cli/install.sh + ./cli/plugin + cli files
if [[ -d "${SCRIPT_DIR}/cli" ]]; then
  CLI_SRC_DIR="${SCRIPT_DIR}/cli"
  PLUGIN_SRC_DIR="${SCRIPT_DIR}/plugin"
else
  CLI_SRC_DIR="${SCRIPT_DIR}"
  PLUGIN_SRC_DIR="${SCRIPT_DIR}/plugin"
fi

INSTALL_BASE="${HOME}/.skillhub"
BIN_DIR="${HOME}/.local/bin"
CLI_TARGET="${INSTALL_BASE}/skills_store_cli.py"
UPGRADE_MODULE_TARGET="${INSTALL_BASE}/skills_upgrade.py"
VERSION_TARGET="${INSTALL_BASE}/version.json"
METADATA_TARGET="${INSTALL_BASE}/metadata.json"
INDEX_TARGET="${INSTALL_BASE}/skills_index.local.json"
CONFIG_TARGET="${INSTALL_BASE}/config.json"
WRAPPER_TARGET="${BIN_DIR}/skillhub"
LEGACY_WRAPPER_TARGET="${BIN_DIR}/oc-skills"

PLUGIN_TARGET_DIR="${HOME}/.openclaw/extensions/skillhub"

find_openclaw_bin() {
  if command -v openclaw >/dev/null 2>&1; then
    command -v openclaw
    return 0
  fi
  if [[ -x "${HOME}/.local/share/pnpm/openclaw" ]]; then
    echo "${HOME}/.local/share/pnpm/openclaw"
    return 0
  fi
  return 1
}

install_cli() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required for skillhub." >&2
    exit 1
  fi

  mkdir -p "${INSTALL_BASE}" "${BIN_DIR}"
  cp "${CLI_SRC_DIR}/skills_store_cli.py" "${CLI_TARGET}"
  cp "${CLI_SRC_DIR}/skills_upgrade.py" "${UPGRADE_MODULE_TARGET}"
  cp "${CLI_SRC_DIR}/version.json" "${VERSION_TARGET}"
  cp "${CLI_SRC_DIR}/metadata.json" "${METADATA_TARGET}"
  cp "${CLI_SRC_DIR}/skills_index.local.json" "${INDEX_TARGET}"
  chmod +x "${CLI_TARGET}"

  if [[ ! -f "${CONFIG_TARGET}" ]]; then
    cat > "${CONFIG_TARGET}" <<'JSON'
{
  "self_update_url": "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/version.json"
}
JSON
  fi

  cat > "${WRAPPER_TARGET}" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail

BASE="${HOME}/.skillhub"
CLI="${BASE}/skills_store_cli.py"

if [[ ! -f "${CLI}" ]]; then
  echo "Error: CLI not found at ${CLI}" >&2
  exit 1
fi

exec python3 "${CLI}" "$@"
WRAPPER

  chmod +x "${WRAPPER_TARGET}"

  cat > "${LEGACY_WRAPPER_TARGET}" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
exec "${HOME}/.local/bin/skillhub" "$@"
WRAPPER

  chmod +x "${LEGACY_WRAPPER_TARGET}"
}

install_plugin() {
  mkdir -p "${PLUGIN_TARGET_DIR}"
  cp "${PLUGIN_SRC_DIR}/index.ts" "${PLUGIN_TARGET_DIR}/index.ts"
  cp "${PLUGIN_SRC_DIR}/openclaw.plugin.json" "${PLUGIN_TARGET_DIR}/openclaw.plugin.json"
}

configure_plugin() {
  local openclaw_bin
  if ! openclaw_bin="$(find_openclaw_bin)"; then
    echo "Warn: openclaw not found on PATH; skipped plugin config." >&2
    return 0
  fi

  "${openclaw_bin}" config set plugins.entries.skillhub.enabled true
  "${openclaw_bin}" config set plugins.entries.skillhub.config.primaryCli 'skillhub'
  "${openclaw_bin}" config set plugins.entries.skillhub.config.fallbackCli 'clawhub'
  "${openclaw_bin}" config set plugins.entries.skillhub.config.primaryLabel 'cn-optimized'
  "${openclaw_bin}" config set plugins.entries.skillhub.config.fallbackLabel 'public-registry'
}

restart_gateway_if_needed() {
  if [[ "${RESTART_GATEWAY}" -ne 1 ]]; then
    return 0
  fi

  local openclaw_bin
  if ! openclaw_bin="$(find_openclaw_bin)"; then
    echo "Warn: openclaw not found on PATH; skipped gateway restart." >&2
    return 0
  fi

  nohup "${openclaw_bin}" gateway run --bind loopback --port 18789 --force >/tmp/openclaw-gateway.log 2>&1 &
}

if [[ "${MODE}" == "all" || "${MODE}" == "cli" ]]; then
  install_cli
fi

if [[ "${MODE}" == "all" || "${MODE}" == "plugin" ]]; then
  install_plugin
  configure_plugin
fi

restart_gateway_if_needed

echo "Install complete."
echo "  mode: ${MODE}"
if [[ "${MODE}" == "all" || "${MODE}" == "cli" ]]; then
  echo "  cli: ${WRAPPER_TARGET}"
  echo "  index: ${INDEX_TARGET}"
fi
if [[ "${MODE}" == "all" || "${MODE}" == "plugin" ]]; then
  echo "  plugin: ${PLUGIN_TARGET_DIR}"
fi
echo
echo "Quick check:"
if [[ "${MODE}" == "all" || "${MODE}" == "cli" ]]; then
  echo "  skillhub search calendar"
fi
if [[ "${MODE}" == "all" || "${MODE}" == "plugin" ]]; then
  echo "  openclaw plugins list | rg skillhub"
fi
