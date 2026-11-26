#!/usr/bin/env bash
# Собирает tarball и SRPM/RPM: ./scripts/make-srpm.sh [--rpm]
set -euo pipefail
cd "$(dirname "$0")/.."
VER=$(sed -n 's/^version = "\(.*\)"/\1/p' tool/pyproject.toml)
TOP=$(rpm --eval '%{_topdir}')
mkdir -p "$TOP"/{SOURCES,SPECS}
git archive --format=tar.gz --prefix="d11ctl-$VER/" -o "$TOP/SOURCES/d11ctl-$VER.tar.gz" HEAD
cp packaging/rpm/d11ctl.spec "$TOP/SPECS/"
if [[ "${1:-}" == "--rpm" ]]; then rpmbuild -ba "$TOP/SPECS/d11ctl.spec"; else rpmbuild -bs "$TOP/SPECS/d11ctl.spec"; fi
