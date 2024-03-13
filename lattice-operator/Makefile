VERSION ?= `cat VERSION`
# Image URL to use all building/pushing image targets
IMG ?= lattice-operator:${VERSION}
IMG_INTERNAL ?= lattice-operator-internal:${VERSION}
# Produce CRDs that work back to Kubernetes 1.11 (no version conversion)
CRD_OPTIONS ?= "crd:trivialVersions=true,preserveUnknownFields=false,generateEmbeddedObjectMeta=true"

REPO ?= breezeml.jfrog.io/breezeml-docker

# Get the currently used golang install path (in GOPATH/bin, unless GOBIN is set)
ifeq (,$(shell go env GOBIN))
GOBIN=$(shell go env GOPATH)/bin
else
GOBIN=$(shell go env GOBIN)
endif

# Setting SHELL to bash allows bash commands to be executed by recipes.
# This is a requirement for 'setup-envtest.sh' in the test target.
# Options are set to exit when a recipe line exits non-zero or a piped command fails.
SHELL = /usr/bin/env bash -o pipefail
.SHELLFLAGS = -ec

all: build

##@ General

# The help target prints out all targets with their descriptions organized
# beneath their categories. The categories are represented by '##@' and the
# target descriptions by '##'. The awk commands is responsible for reading the
# entire set of makefiles included in this invocation, looking for lines of the
# file as xyz: ## something, and then pretty-format the target and help. Then,
# if there's a line with ##@ something, that gets pretty-printed as a category.
# More info on the usage of ANSI control characters for terminal formatting:
# https://en.wikipedia.org/wiki/ANSI_escape_code#SGR_parameters
# More info on the awk command:
# http://linuxcommand.org/lc3_adv_awk.php

help: ## Display this help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development

manifests: controller-gen ## Generate WebhookConfiguration, ClusterRole and CustomResourceDefinition objects.
	$(CONTROLLER_GEN) $(CRD_OPTIONS) rbac:roleName=manager-role webhook paths="./pkg/apis/..." output:crd:artifacts:config=manifests/base/crds


generate:
	hack/update-codegen.sh

apidoc:
	hack/generate-apidoc.sh

fmt: ## Run go fmt against code.
	go fmt ./...

vet: ## Run go vet against code.
	go vet ./...

GOLANGCI_LINT=$(shell which golangci-lint)
golangci-lint:
ifeq ($(GOLANGCI_LINT),)
	curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/master/install.sh | sh -s -- -b $(shell go env GOPATH)/bin v1.50.1
	$(info golangci-lint has been installed)
endif
	golangci-lint run --timeout 5m ./...

STATICCHECK = $(shell pwd)/bin/staticcheck
staticcheck: ## Download staticcheck
	$(call go-get-tool,$(STATICCHECK),honnef.co/go/tools/cmd/staticcheck@v0.4.3)
	$(STATICCHECK) ./...

ENVTEST_K8S_VERSION ?= 1.22
HAS_SETUP_ENVTEST := $(shell command -v setup-envtest;)

testall: manifests generate fmt vet golangci-lint test ## Run tests.

test: manifests envtest
	KUBEBUILDER_ASSETS="$(shell setup-envtest --arch=amd64 use $(ENVTEST_K8S_VERSION) -p path)" go test ./... -coverprofile cover.out

envtest:
ifndef HAS_SETUP_ENVTEST
	go install sigs.k8s.io/controller-runtime/tools/setup-envtest@3966c6775dfb86e6ce171c5673ae52c0724b2d9f # v0.12.1
	@echo "setup-envtest has been installed"
endif
	@echo "setup-envtest has already installed"

KWOK_REPO := $(shell echo "kubernetes-sigs/kwok")
KWOK_LATEST_RELEASE := $(shell curl "https://api.github.com/repos/${KWOK_REPO}/releases/latest" | jq -r '.tag_name')
KWOKCTL = $(shell pwd)/bin/kwokctl
kwok:  # Get kwok test environment. We can test gpu scheduling with a fake node.
	mkdir -p $(shell pwd)/bin
	wget -O $(PROJECT_DIR)/bin/kwokctl -c "https://github.com/$(KWOK_REPO)/releases/download/$(KWOK_LATEST_RELEASE)/kwokctl-$(shell go env GOOS)-$(shell go env GOARCH)"
	chmod +x $(PROJECT_DIR)/bin/kwokctl
	wget -O $(PROJECT_DIR)/bin/kwok -c "https://github.com/$(KWOK_REPO)/releases/download/$(KWOK_LATEST_RELEASE)/kwok-$(shell go env GOOS)-$(shell go env GOARCH)"
	chmod +x $(PROJECT_DIR)/bin/kwok

YQ_BIN = $(shell pwd)/bin/yq
YQ_VERSION = v4.33.2
yq: ## Download yq, a yaml processor used by us to generate build secrets from config files.
	mkdir -p $(shell pwd)/bin
	wget -O $(YQ_BIN) -c "https://github.com/mikefarah/yq/releases/download/$(YQ_VERSION)/yq_$(shell go env GOOS)_$(shell go env GOARCH)"
	chmod +x $(YQ_BIN)

build: generate fmt vet ## Build manager binary.
	go build -o bin/manager cmd/training-operator.v1/main.go

build-target-platform: ## Build manager binary with target platform, used for docker build
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GO111MODULE=on go build -o bin/manager cmd/training-operator.v1/main.go

build-release: yq generate fmt vet ## Build manager binary for release.
	go build -tags release -o bin/manager -ldflags "$(shell scripts/compose-build-secrets.sh)" cmd/training-operator.v1/main.go

build-release-target-platform: yq generate fmt vet ## Build manager binary for release with target platform, used for docker build
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GO111MODULE=on go build -tags release -o bin/manager -ldflags "$(shell scripts/compose-build-secrets.sh)" cmd/training-operator.v1/main.go

run: manifests generate fmt vet ## Run a controller from your host.
	go run ./cmd/training-operator.v1/main.go

docker-build: test ## Build docker image with the manager.
	docker build -t ${IMG_INTERNAL} -f build/images/training-operator/Dockerfile .

docker-build-release: test ## Build docker image with the manager.
	docker build -t ${IMG} -f build/images/training-operator/Dockerfile . --build-arg IS_RELEASE=true

docker-push: docker-build docker-build-release ## Push docker image with the manager.
	docker tag ${IMG} ${REPO}/${IMG}
	docker push ${REPO}/${IMG}
	docker tag ${IMG_INTERNAL} ${REPO}/${IMG_INTERNAL}
	docker push ${REPO}/${IMG_INTERNAL}

github-actions: ## Test github actions locally
	curl -s https://raw.githubusercontent.com/nektos/act/master/install.sh | bash
	bin/act -j checks

##@ Deployment

install: manifests kustomize ## Install CRDs into the K8s cluster specified in ~/.kube/config.
	$(KUSTOMIZE) build manifests/base/crds | kubectl apply -f -

uninstall: manifests kustomize ## Uninstall CRDs from the K8s cluster specified in ~/.kube/config.
	$(KUSTOMIZE) build manifests/base/crds | kubectl delete -f -

deploy: manifests kustomize ## Deploy controller to the K8s cluster specified in ~/.kube/config.
	cd manifests/overlays/standalone && $(KUSTOMIZE) edit set image kubeflow/training-operator=${IMG}
	$(KUSTOMIZE) build manifests/overlays/standalone | kubectl apply -f -

undeploy: ## Undeploy controller from the K8s cluster specified in ~/.kube/config.
	$(KUSTOMIZE) build manifests/overlays/standalone | kubectl delete -f -


CONTROLLER_GEN = $(shell pwd)/bin/controller-gen
controller-gen: ## Download controller-gen locally if necessary.
	$(call go-get-tool,$(CONTROLLER_GEN),sigs.k8s.io/controller-tools/cmd/controller-gen@v0.6.0)

KUSTOMIZE = $(shell pwd)/bin/kustomize
kustomize: ## Download kustomize locally if necessary.
	$(call go-get-tool,$(KUSTOMIZE),sigs.k8s.io/kustomize/kustomize/v4@v4.5.7)

# go-get-tool will 'go get' any package $2 and install it to $1.
PROJECT_DIR := $(shell dirname $(abspath $(lastword $(MAKEFILE_LIST))))
define go-get-tool
@[ -f $(1) ] || { \
set -e ;\
TMP_DIR=$$(mktemp -d) ;\
cd $$TMP_DIR ;\
go mod init tmp ;\
echo "Downloading $(2)" ;\
GOBIN=$(PROJECT_DIR)/bin go install $(2) ;\
rm -rf $$TMP_DIR ;\
}
endef
