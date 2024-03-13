VERSION ?= `cat VERSION`
# Image URL to use all building/pushing image targets
IMG ?= lattice-api-server:${VERSION}
# Produce CRDs that work back to Kubernetes 1.11 (no version conversion)
CRD_OPTIONS ?= "crd:trivialVersions=true,preserveUnknownFields=false,generateEmbeddedObjectMeta=true"

REPO ?= breezeml.jfrog.io/breezeml-docker

test: ## Run unit tests and static checks.
	go test go test -race -vet=off ./test...
	staticcheck ./...

lint: ## Run golang lint.
	golangci-lint run

docker-build: ## Build docker image with the manager.
	docker build -t ${IMG} -f docker/Dockerfile .

docker-push: ## Push docker image with the manager.
	docker tag ${IMG} ${REPO}/${IMG}
	docker push ${REPO}/${IMG}
