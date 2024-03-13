#!/bin/bash
set -euo pipefail

# Include operator helm chart docs
cp modules/operator/helm/lattice-operator/README.md ./docs/ref/operator.md

# Remove github tags from docs
awk '!/\[!\[app version\]/' ./docs/ref/operator.md > ./docs/ref/operator.md.tmp
mv ./docs/ref/operator.md.tmp ./docs/ref/operator.md

awk '!/\[!\[helm\]/' ./docs/ref/operator.md > ./docs/ref/operator.md.tmp
mv ./docs/ref/operator.md.tmp ./docs/ref/operator.md
