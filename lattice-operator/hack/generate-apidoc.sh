#!/bin/bash

# Copyright 2017 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This shell is used to auto generate some useful tools for k8s, such as lister,
# informer, deepcopy, defaulter and so on.

set -o errexit
set -o nounset
set -o pipefail

SCRIPT_ROOT=$(dirname ${BASH_SOURCE})/..

cd ${SCRIPT_ROOT}

CRD_REF_GEN_VERSION=v0.0.8
go install github.com/elastic/crd-ref-docs@${CRD_REF_GEN_VERSION}

output=./docs/api/breezeml.ai_v1_generated.md
crd-ref-docs \
    --source-path ./pkg/apis/breezeml.ai/v1/ \
		--config ./docs/api/autogen/config.yaml \
		--output-path $output \
		--renderer markdown \
		--max-depth 30

cd - > /dev/null
