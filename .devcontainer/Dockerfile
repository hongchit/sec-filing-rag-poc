FROM mcr.microsoft.com/devcontainers/python:3-3.14-trixie

ENV PYTHONUNBUFFERED=1

ARG GITLEAKS_VERSION=8.30.1
ARG GITLEAKS_SHA256_AMD64=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
ARG GITLEAKS_SHA256_ARM64=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080

RUN apt-get update \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends ca-certificates curl postgresql-client \
    && architecture="$(dpkg --print-architecture)" \
    && case "${architecture}" in \
        amd64) archive_arch="x64"; archive_sha256="${GITLEAKS_SHA256_AMD64}" ;; \
        arm64) archive_arch="arm64"; archive_sha256="${GITLEAKS_SHA256_ARM64}" ;; \
        *) echo "Unsupported Gitleaks architecture: ${architecture}" >&2; exit 1 ;; \
    esac \
    && archive="gitleaks_${GITLEAKS_VERSION}_linux_${archive_arch}.tar.gz" \
    && curl -fsSL \
        "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${archive}" \
        -o /tmp/gitleaks.tar.gz \
    && echo "${archive_sha256}  /tmp/gitleaks.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/gitleaks.tar.gz -C /usr/local/bin gitleaks \
    && chmod 0755 /usr/local/bin/gitleaks \
    && gitleaks version \
    && rm -f /tmp/gitleaks.tar.gz \
    && rm -rf /var/lib/apt/lists/*

# [Optional] If your requirements rarely change, uncomment this section to add them to the image.
# COPY requirements.txt /tmp/pip-tmp/
# RUN pip3 --disable-pip-version-check --no-cache-dir install -r /tmp/pip-tmp/requirements.txt \
#    && rm -rf /tmp/pip-tmp

# [Optional] Uncomment this section to install additional OS packages.
# RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
#     && apt-get -y install --no-install-recommends <your-package-list-here>

# Ensure that persistent cache and tool directories are owned by the vscode user.
RUN install -d -o vscode -g vscode \
    /home/vscode/.cache \
    /home/vscode/.cache/cargo \
    /home/vscode/.local/cargo-tools
