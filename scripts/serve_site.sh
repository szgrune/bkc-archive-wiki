#!/usr/bin/env bash
set -euo pipefail

BKC_SITE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BKC_QUARTZ_REF="v4.5.2"
BKC_QUARTZ_PATH="${BKC_QUARTZ_CACHE:-$BKC_SITE_ROOT/.quartz-local}"
BKC_SITE_PORT_VALUE="${BKC_SITE_PORT:-8080}"
BKC_NPM_CACHE_PATH="${BKC_NPM_CACHE_DIR:-$BKC_QUARTZ_PATH/.npm-cache}"

if [[ ! "$BKC_SITE_PORT_VALUE" =~ ^[0-9]+$ ]] || (( BKC_SITE_PORT_VALUE < 1 || BKC_SITE_PORT_VALUE > 65535 )); then
  echo "BKC_SITE_PORT must be an integer from 1 to 65535" >&2
  exit 2
fi

if [[ "$BKC_QUARTZ_PATH" == "/" || "$BKC_QUARTZ_PATH" == "$BKC_SITE_ROOT" ]]; then
  echo "Refusing unsafe BKC_QUARTZ_CACHE path: $BKC_QUARTZ_PATH" >&2
  exit 2
fi

for BKC_REQUIRED_COMMAND in git node npm npx rsync; do
  if ! command -v "$BKC_REQUIRED_COMMAND" >/dev/null 2>&1; then
    echo "Missing required command: $BKC_REQUIRED_COMMAND" >&2
    exit 1
  fi
done

if [[ ! -d "$BKC_QUARTZ_PATH/.git" ]]; then
  if [[ -e "$BKC_QUARTZ_PATH" ]]; then
    echo "$BKC_QUARTZ_PATH exists but is not a Quartz git checkout" >&2
    exit 1
  fi
  echo "Cloning Quartz $BKC_QUARTZ_REF into $BKC_QUARTZ_PATH"
  git clone --depth 1 --branch "$BKC_QUARTZ_REF" \
    https://github.com/jackyzha0/quartz.git "$BKC_QUARTZ_PATH"
fi

if [[ ! -f "$BKC_QUARTZ_PATH/node_modules/.package-lock.json" ]]; then
  echo "Installing Quartz dependencies"
  (cd "$BKC_QUARTZ_PATH" && env npm_config_cache="$BKC_NPM_CACHE_PATH" npm ci)
fi

echo "Assembling wiki content"
rm -rf "$BKC_QUARTZ_PATH/content" "$BKC_QUARTZ_PATH/public"
mkdir -p "$BKC_QUARTZ_PATH/content"
rsync -a \
  --exclude='/.*' \
  --exclude='.git/' \
  --exclude='.github/' \
  --exclude='.quartz/' \
  --exclude='.quartz-local/' \
  --exclude='api/' \
  --exclude='inbox/' \
  --exclude='raw/archive.json' \
  "$BKC_SITE_ROOT/" "$BKC_QUARTZ_PATH/content/"

if [[ -f "$BKC_SITE_ROOT/.quartz/custom.scss" ]]; then
  cp "$BKC_SITE_ROOT/.quartz/custom.scss" "$BKC_QUARTZ_PATH/quartz/styles/custom.scss"
fi

node "$BKC_SITE_ROOT/scripts/configure_quartz.mjs" "$BKC_QUARTZ_PATH" \
  --base-url "localhost:$BKC_SITE_PORT_VALUE" \
  --graph-depth 1 \
  --skip-og-images

echo "Serving BKC Archive Wiki at http://localhost:$BKC_SITE_PORT_VALUE"
cd "$BKC_QUARTZ_PATH"
exec env npm_config_cache="$BKC_NPM_CACHE_PATH" \
  npx --no-install quartz build --serve --port "$BKC_SITE_PORT_VALUE"
