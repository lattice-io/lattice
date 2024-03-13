# Lattice Operator

Forked from [Kubeflow Training Operator](https://github.com/kubeflow/training-operator)

## Development

### Prerequisites

- Kubernetes >= 1.22
- Go == 1.19

Make sure you have set up the following env var:

- `$GOPATH`, which by default should be `$HOME/go`
- `$PATH` should include `$GOPATH/bin`

### Project Structure

The skeleton of this project is created with [Kubebuilder](https://github.com/kubernetes-sigs/kubebuilder). However, current project organization does not follow Kubebuilder.

There are some files in this project are generated, including:

- Kubernetes clientset, listers, informers, see `pkg/client/**` and deepcopy implementations, see `pkg/apis/**/zz_generated.deepcopy.go`; generated with [generate-groups.sh](https://github.com/kubernetes/code-generator/blob/master/generate-groups.sh) in [code-generator](https://github.com/kubernetes/code-generator).
- Defaulters; see `pkg/apis/**/zz_generated.defaults.go`; generated with [defaulter-gen](https://github.com/kubernetes/code-generator/tree/master/cmd/defaulter-gen) from [code-generator](https://github.com/kubernetes/code-generator).
- OpenAPI definitions; see `pkg/apis/kubeflow.org/v1/openapi_generated.go`, which used in `hack/swagger/main.go`; generated with [openapi-gen](https://github.com/kubernetes/code-generator/tree/master/cmd/openapi-gen) from [code-generator](https://github.com/kubernetes/code-generator).

I temporarily removed some generated to forbid inconsistency in the helm chart. You can still use tools to generate them for reference:

- API docs; to generate, run `make api doc`
- CRD manifests; to generate, run `make manifests`

### Develop the operator outside a cluster

First, make sure you can connect to a Kubernetes cluster correctly, for example, using `kubectl`.

Then install CRDs:

```sh
make install
```

This command will install the CRDs. To get current installed CRDs, run:

```sh
kubectl get crds
```

With the CRDs installed, you can run the operator:

```sh
go run cmd/training-operator.v1/main.go
```

Note that there are some environment variables you can set up to configure lattice-operator.
| Key  | Example | Description |
|------|---------|-------------|
| RESOURCE_SCHEDULING_UNIT | "node", "nvidia.com/gpu", etc. | The resource unit that the operator used to schedule TrainingJobs. Note that if the value is set other than "node", users need to specify the resource requests and limits in their TrainingJob description. |
| LATTICE_JOB_NODE_SELECTOR_PATH | "/etc/config/node-selector.conf" | Path to the file that describe the node selector TrainingJob's pods should be distributed to. Each line of the file should look like "key=value" |
| LATTICE_JFROG_SECRET_PATH | "/etc/config/job-secret" | Path to the folder that contains the files "username" and "password" (for JFrog). It is used to give pods permission to download lattice-addon and lattice-agent when their TrainingJob's injectLattice field is set true. |
| ADDONS_CHECKPOINT_TYPE | "remote" | The checkpoint type used by lattice-addon. |
| CHECKPOINT_SERVICE_ENDPOINT | "lattice-checkpoint-svc.lattice" | The checkpoint endpoint used by lattice-addon. |
| CHECKPOINT_SERVICE_PORT | "5555" | The checkpoint endpoint's port used by lattice-addon. |
| RDZV_BACKEND | "etcd" | The Rendezvous backend type used by lattice-agent. |
| RDZV_SERVICE_ENDPOINT | "lattice-rdzv-client.lattice" | The Rendezvous endpoint configured for lattice-agent. |
| RDZV_SERVICE_PORT | "2379" | The Rendezvous port configured for lattice-agent. |

To run all unit tests:
```sh
make test
```


### Build the binary for release
The release version of the operator has periodic license checks. We issue licenses through [Lemon Squeezy](https://www.lemonsqueezy.com/). A valid license 
for development can be found from "Lattice Operator License" in BreezeML's 1password account.

To build the release binary, you will need to add a `release` tag:
```sh
go build -tags release -a -o manager cmd/training-operator.v1/main.go
```

To build a docker image of the release version:
```sh
make docker-build-release
```

To build a docker image of the non-release version:
```sh
make docker-build
```

Note that with the release version, you will need a `LATTICE_LICENSE` environment that sets up the license key from Lemon Squeezy.

### Install in Minikube from source
First, clone the repo:

```sh
git clone git@github.com:breezeml/lattice-operator.git
```

To use a docker image built from the current source code, build docker image:
```sh
make docker-build
```

This will build a docker image with tag "lattice-operator-internal:<VERSION>".

Also, please modify the following entries in helm/lattice-operator/values.yaml 
to use a local copy of lattice-operator:
```yaml
image: lattice-operator-internal
imagePullPolicy: Never
```

Please also modify jfrog.username and jfrog.password in helm/lattice-operator/values.yaml.

Load your image into your cluster. For example, in minikubes,
```sh
minikube image load lattice-operator-internal:`cat VERSION`
```

Finally, install the chart:

```sh
cd helm/lattice-operator
helm install operator . --namespace lattice --create-namespace
```

To get the status of the deployment, run:

```sh
kubectl get deployment lattice-operator --namespace lattice
```

### Manage jobs
Each job is represented by a TrainingJob resource in the cluster. 
Please refer to "examples/lattice/env/trainingjob.yaml" for an example TrainingJob. Each job should have a 
minSize and a maxSize, representing the range of node numbers the job can run on. Each job should also specify 
information about its docker container in replicaSpecs->template->spec (the container name must be trainingjob). 
For now, we need to assume that user's docker images/containers itself already handles elasticity behavior (e.g., by 
installing and running upon lattice-agent).

You can check an example TrainingJob yaml file at examples/lattice/env/trainingjob.yaml.

To create a job in the cluster:
```sh
kubectl apply -f examples/lattice/env/trainingjob.yaml
```

To modify a job in the cluster, edit the yaml file and then:
```sh
kubectl apply -f examples/lattice/env/trainingjob.yaml
```

To delete a job from the cluster:
```sh
kubectl delete -f examples/lattice/env/trainingjob.yaml
```

Currently, we only manage data-parallel training jobs in machine learning. Later, we might support other different 
training paradigms such as model-parallel and pipline in our TrainingJob.

## Third-party service requisite
Our release version periodically validates the license and pushes usage metrics. As a result, it will require the following services:
 - Grafana Cloud: we hold a Grafana Cloud instance to collect GPU-hour usage for billing. Our operator will periodically push data to our Grafana Cloud remote write endpoint.
 - Lemon Squeezy: we use Lemon Squeezy to check and validate license keys.

Our account information for both Grafana Cloud and Lemon Squeezy can be found through 1password.

The related endpoints, auth information, etc. are encoded into the executable at build-time. Please check `build/config.yaml` for more information about the encoded data. In the situation 
where our third-party service endpoint changes, we need to modify the entries in `build/config.yaml` and re-build the operator project.
