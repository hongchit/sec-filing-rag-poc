#!/usr/bin/env bash
set -euo pipefail

repository_root=$(git rev-parse --show-toplevel)
cd "${repository_root}"

if command -v kubectl >/dev/null 2>&1; then
  render=(kubectl kustomize)
elif command -v kustomize >/dev/null 2>&1; then
  render=(kustomize build)
else
  echo "install kubectl or kustomize to validate deployment manifests" >&2
  exit 2
fi

for profile in 4gb 8gb; do
  rendered=$(mktemp)
  trap 'rm -f "${rendered}"' EXIT

  # Render each supported resource profile and apply static deployment invariants.
  "${render[@]}" "deploy/k3s/overlays/${profile}" >"${rendered}"
  grep -q 'namespace: project-sec-filing-rag-poc' "${rendered}"
  grep -q 'host: sec-filing-rag-poc.henrychan.dev' "${rendered}"
  grep -q 'kustomize.toolkit.fluxcd.io/prune: disabled' "${rendered}"
  grep -q 'name: evaluation-data' "${rendered}"
  grep -q 'name: initialize-evaluation' "${rendered}"
  grep -q 'sec-rag-production-evaluation' "${rendered}"
  grep -q 'storage: 1Gi' "${rendered}"
  grep -q 'mountPath: /app/evaluation-data' "${rendered}"
  grep -q 'value: /app/evaluation-data/active/config/retrieval.json' "${rendered}"
  grep -q 'value: /app/evaluation-data/active/config/generation.json' "${rendered}"
  if grep -E 'image: .+:(latest|bootstrap)([[:space:]]|$)' "${rendered}" >/dev/null; then
    echo "${profile}: rendered workload contains a mutable image tag" >&2
    exit 1
  fi
  rm -f "${rendered}"
  trap - EXIT
done

echo "K3s manifests render successfully for 4gb and 8gb profiles"
