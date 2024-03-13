#!/bin/bash

# Copyright 2023 The BreezeML Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This script is to compose build secrets related to Grafana Cloud and Lemon Squeezy
# It is used in the build pipeline in order to generate ldflags for the build
# You need to have yq installed in order to run this script by running "make yq"

# Generate ldflags for grafana cloud
ldflags="-X main.grafanaCloudURL=$(bin/yq .grafanaCloud.pushUrl build/config.yaml)"
ldflags+=" -X main.grafanaCloudUserName=$(bin/yq .grafanaCloud.userName build/config.yaml)"
ldflags+=" -X main.grafanaCloudPassword=$(bin/yq .grafanaCloud.password build/config.yaml)"

# Generate ldflags for lemon squeezy
ldflags+=" -X main.lemonSqueezyStoreID=$(bin/yq .lemonSqueezy.storeID build/config.yaml)"
ldflags+=" -X main.lemonSqueezyProductID=$(bin/yq .lemonSqueezy.productID build/config.yaml)"
ldflags+=" -X main.lemonSqueezyProductName=$(bin/yq .lemonSqueezy.productName build/config.yaml)"

echo -n $ldflags
