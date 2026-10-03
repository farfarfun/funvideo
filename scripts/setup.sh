#!/usr/bin/env bash
set -euo pipefail

CLI_NAME="funvideo"
PACKAGE_NAME="funvideo"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
PORT="${FUNVIDEO_PORT:-8080}"
CONFIG_PATH="${FUNVIDEO_CONFIG_FILE:-}"
RUNTIME_DIR="${FUNVIDEO_RUNTIME_DIR:-${ROOT_DIR}/.run}"

readonly CLI_NAME PACKAGE_NAME ROOT_DIR PORT CONFIG_PATH RUNTIME_DIR
export FUNVIDEO_RUNTIME_DIR="${RUNTIME_DIR}"

usage() {
  cat >&2 <<'EOF'
用法：scripts/setup.sh <动作> [dev|prod]

服务：start | stop | restart | run（必须指定 dev 或 prod）；status（可省略环境）
安装：install-dev | install-prod [版本]
发布：publish
维护：upgrade [版本] | rollback <版本> | uninstall
EOF
}

die() {
  printf '错误：%s\n' "$*" >&2
  exit 2
}

cli_options() {
  CLI_OPTIONS=(--port "${PORT}")
  if [[ -n "${CONFIG_PATH}" ]]; then
    CLI_OPTIONS+=(--config "${CONFIG_PATH}")
  fi
}

run_server_action() {
  local action="$1"
  local environment="${2:-}"
  cli_options
  if [[ "${action}" == "status" && -z "${environment}" ]]; then
    "${CLI_NAME}" server status "${CLI_OPTIONS[@]}"
    return
  fi
  if [[ "${action}" == "run" ]]; then
    exec "${CLI_NAME}" server run "${environment}" "${CLI_OPTIONS[@]}"
  fi
  "${CLI_NAME}" server "${action}" "${environment}" "${CLI_OPTIONS[@]}"
}

install_prod() {
  local version="${1:-}"
  if [[ -z "${version}" ]] && uv tool list | grep -q "^${PACKAGE_NAME} "; then
    printf '%s 已安装；未指定版本，不执行升级。\n' "${PACKAGE_NAME}"
    return
  fi
  if [[ -n "${version}" ]]; then
    uv tool install "${PACKAGE_NAME}==${version}"
  else
    uv tool install "${PACKAGE_NAME}"
  fi
}

main() {
  local action="${1:-}"
  shift || true

  case "${action}" in
  start | stop | restart | run)
    (( $# == 1 )) || die "${action} 必须指定 dev 或 prod"
    [[ "$1" == "dev" || "$1" == "prod" ]] || die "运行环境必须是 dev 或 prod"
    run_server_action "${action}" "$1"
    ;;
  status)
    (( $# <= 1 )) || die "status 最多接受一个 dev 或 prod 参数"
    [[ $# == 0 || "$1" == "dev" || "$1" == "prod" ]] || die "运行环境必须是 dev 或 prod"
    run_server_action "${action}" "${1:-}"
    ;;
  install-dev)
    (( $# == 0 )) || die "install-dev 不接受额外参数"
    funbuild install
    ;;
  install-prod)
    (( $# <= 1 )) || die "install-prod 最多接受一个版本号"
    install_prod "${1:-}"
    ;;
  publish)
    (( $# == 0 )) || die "publish 不接受额外参数"
    funbuild build
    ;;
  upgrade)
    (( $# <= 1 )) || die "upgrade 最多接受一个版本号"
    "${CLI_NAME}" upgrade "$@"
    ;;
  rollback)
    (( $# == 1 )) || die "rollback 必须指定版本号"
    "${CLI_NAME}" rollback "$1"
    ;;
  uninstall)
    (( $# == 0 )) || die "uninstall 不接受额外参数"
    "${CLI_NAME}" uninstall
    ;;
  -h | --help | help)
    usage
    ;;
  *)
    usage
    die "未知动作：${action:-<空>}"
    ;;
  esac
}

main "$@"
