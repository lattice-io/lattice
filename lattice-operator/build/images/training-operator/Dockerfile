# Build the manager binary
FROM golang:1.19 as builder

ARG IS_RELEASE

WORKDIR /workspace
# Copy the Go Modules manifests
COPY go.mod go.mod
COPY go.sum go.sum
# cache deps before building and copying source so that we don't need to re-download as much
# and so that source changes don't invalidate our downloaded layer
RUN go mod download

# Copy the go source
COPY . .

# Build
RUN if [ "$IS_RELEASE" = "true" ]; then \
      echo "Building release image" && \
      make build-release-target-platform; \
    else \
      echo "Building dev image" && \
      make build-target-platform; \
    fi

# Use distroless as minimal base image to package the manager binary
# Refer to https://github.com/GoogleContainerTools/distroless for more details
FROM gcr.io/distroless/static:latest
WORKDIR /
COPY --from=builder /workspace/bin/manager .
ENTRYPOINT ["/manager"]
