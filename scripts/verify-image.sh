#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <local-image-reference>" >&2
  exit 2
fi

image_ref=$1
container_id=""
rootfs_archive=$(mktemp --suffix=.tar)
metadata_file=$(mktemp --suffix=.json)
rootfs_listing=$(mktemp --suffix=.txt)

cleanup() {
  if [[ -n "${container_id}" ]]; then
    docker container rm --force "${container_id}" >/dev/null 2>&1 || true
  fi
  rm -f "${rootfs_archive}" "${metadata_file}" "${rootfs_listing}"
}
trap cleanup EXIT

# Inspect image configuration without printing potentially sensitive metadata.
docker image inspect "${image_ref}" >"${metadata_file}"
if jq -e '.[0].Config.Env[]? | test("^(OPENAI_API_KEY|GOOGLE_CLIENT_SECRET|SESSION_SECRET|INGESTION_API_TOKEN|POSTGRES_PASSWORD|APP_DATABASE_PASSWORD|KESTRA_DATABASE_PASSWORD|KESTRA_BASIC_AUTH_PASSWORD)=")' "${metadata_file}" >/dev/null; then
  echo "image metadata contains a forbidden runtime-secret environment key" >&2
  exit 1
fi

# Export the final filesystem and reject credential files or development material.
container_id=$(docker container create "${image_ref}")
docker container export --output "${rootfs_archive}" "${container_id}"
tar -tf "${rootfs_archive}" >"${rootfs_listing}"
if grep -Ei '(^|/)(\.env($|\.)|\.git(/|$)|id_rsa($|\.)|[^/]+\.(key|p12|pfx|jks|keystore)$|(private|secret|credential)[^/]*\.pem$)' "${rootfs_listing}" >/dev/null; then
  echo "image filesystem contains a forbidden credential or metadata path" >&2
  exit 1
fi

echo "image metadata and final filesystem checks passed: ${image_ref}"
