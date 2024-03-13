VERSION := $(shell cat VERSION)

IMG ?= lattice-dashboard:${VERSION}

REPO ?= breezeml.jfrog.io/breezeml-docker

NAME ?= lattice-dashboard

docker-build:
	docker build -t ${IMG} .

docker-run:
	docker run -p 8000:80 --rm --name ${NAME} ${IMG}

docker-push:
	docker tag ${IMG} ${REPO}/${IMG}
	docker push ${REPO}/${IMG}
