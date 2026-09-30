#!/usr/bin/env bash
set -euo pipefail

CLI_NAME="funvideo"
PACKAGE_NAME="funvideo"
PORT="${FUNVIDEO_PORT:-8080}"
CONFIG_PATH="${FUNVIDEO_CONFIG_FILE:-}"

readonly CLI_NAME PACKAGE_NAME PORT CONFIG_PATH

usage() {
  cat >&2 <<'EOF'
用法：scripts/setup.sh <动作> <dev|prod>

服务：start | stop | restart | run | status（必须指定 dev 或 prod）
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
  local environment="$2"
  cli_options
  if [[ "${action}" == "run" ]]; then
    exec "${CLI_NAME}" server run "${environment}" "${CLI_OPTIONS[@]}"
  fi
  "${CLI_NAME}" server "${action}" "${environment}" "${CLI_OPTIONS[@]}"
}

install_prod() {
  local version="${1:-}"
  if [[ -z "${version}" ]] && python3 -m pip show "${PACKAGE_NAME}" >/dev/null 2>&1; then
    printf '%s 已安装；未指定版本，不执行升级。\n' "${PACKAGE_NAME}"
    return
  fi
  if [[ -n "${version}" ]]; then
    python3 -m pip install "${PACKAGE_NAME}==${version}"
  else
    python3 -m pip install "${PACKAGE_NAME}"
  fi
}

main() {
  local action="${1:-}"
  shift || true

  case "${action}" in
  start | stop | restart | run | status)
    (( $# == 1 )) || die "${action} 必须指定 dev 或 prod"
    [[ "$1" == "dev" || "$1" == "prod" ]] || die "运行环境必须是 dev 或 prod"
    run_server_action "${action}" "$1"
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
