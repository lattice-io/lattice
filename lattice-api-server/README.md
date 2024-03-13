## Introduction

The repository contains the lattice api server based on Django. The api server takes
api requests from lattice-dashboard frontend, and create, modify, monitor, or delete
latticejobs by communicating with the k8s cluster and lattice-monitor.

## Quick Start

Create a local Docker image

```bash
docker build -t lattice-api-server:latest -f ./docker/Dockerfile .
```

check the built image
```bash
docker images

REPOSITORY                             TAG       IMAGE ID       CREATED         SIZE
lattice-api                            latest    42c2ef641b54   4 minutes ago   894MB
```

```bash
docker run -it --rm -p 8080:8080 lattice-api-server:latest

[GIN-debug] [WARNING] Creating an Engine instance with the Logger and Recovery middleware already attached.

[GIN-debug] [WARNING] Running in "debug" mode. Switch to "release" mode in production.
 - using env:   export GIN_MODE=release
 - using code:  gin.SetMode(gin.ReleaseMode)

[GIN-debug] GET    /                         --> main.main.func1 (4 handlers)
[GIN-debug] GET    /api/job                  --> main.getJobs (4 handlers)
[GIN-debug] POST   /api/job                  --> main.postJob (4 handlers)
[GIN-debug] DELETE /api/job                  --> main.deleteJobs (4 handlers)
[GIN-debug] PATCH  /api/job                  --> main.updateJob (4 handlers)
[GIN-debug] GET    /api/log/:namespace/:jobId --> main.getLog (4 handlers)
[GIN-debug] POST   /api/job/resnet           --> main.postResnet (4 handlers)
[GIN-debug] POST   /api/job/bert             --> main.postBert (4 handlers)
[GIN-debug] POST   /api/cluster              --> main.scaleCluster (4 handlers)
[GIN-debug] GET    /api/cluster              --> main.clusterSize (4 handlers)
[GIN-debug] GET    /api/datasets             --> main.listDatasets (4 handlers)
[GIN-debug] POST   /api/datasets             --> main.uploadDatasets (4 handlers)
[GIN-debug] GET    /api/datasets/:dataset_name --> main.downloadDatasets (4 handlers)
[GIN-debug] [WARNING] You trusted all proxies, this is NOT safe. We recommend you to set a value.
Please check https://pkg.go.dev/github.com/gin-gonic/gin#readme-don-t-trust-all-proxies for details.
[GIN-debug] Listening and serving HTTP on 0.0.0.0:8080
```

List jobs:

```bash
curl --location 'localhost:8080/api/job'
```

Create a job:

```bash
curl -X POST \
  'http://localhost:8080/api/job' \
  --header 'Content-Type: application/json' \
  --data-raw '{
  "apiVersion": "breezeml.ai/v1",
  "kind": "TrainingJob",
  "metadata": {
    "name": "lattice-job",
    "namespace": "lattice"
  },
  "spec": {
    "runPolicy": {
      "cleanPodPolicy": "None"
    },
    "minSize": 3,
    "maxSize": 4,
    "replicaSpecs": {
      "template": {
        "spec": {
          "containers": [
            {
              "name": "trainingjob",
              "image": "ubuntu:18.04",
              "imagePullPolicy": "Always",
              "command": [
                "sleep"
              ],
              "args": [
                "60"
              ]
            }
          ]
        }
      }
    }
  }
}'
```

Delete a job:

```bash
curl -X DELETE 'http://localhost:8080/api/job?name=lattice-job'
```

Update a job:
```bash
curl --location --request PATCH 'localhost:8080/api/job' \
--header 'Content-Type: application/json' \
--data '{
  "apiVersion": "breezeml.ai/v1",
  "kind": "TrainingJob",
  "metadata": {
    "name": "lattice-simple1",
    "namespace": "lattice"
  },
  "spec": {
    "priority": 2
  }
}'
```

Get logs for a job:
```bash
curl --location 'localhost:8080/api/log/<namespace>/<job_name>'
```

List all datasets from s3 bucket:
```bash
curl -X GET --location 'http://localhost:8080/api/datasets'
```

Upload a single zip/tar dataset file to s3 bucket:
```bash
curl -X POST -F 'file=@<dataset_file>' --location 'http://localhost:8080/api/datasets'
```

Generate a presigned link containing the dataset downloaded from s3 bucket:
```bash
curl -X GET --location 'http://localhost:8080/api/datasets/<dataset_name>'
```

## Deploying to Local Minikube

Load the image to minikube Docker env

```bash
minikube image load lattice-api-server:latest
```

Create a deployment

```bash
kubectl apply -f ./docker/deployment.yaml
```

Forward the port to `localhost`

```bash
kubectl port-forward deployment/lattice-api-server 8080:8080
```


## Deploying to Remote EKS Cluster
```bash
# https://stackoverflow.com/questions/57167104/how-to-use-local-docker-image-in-kubernetes-via-kubectl

docker run -d -p 5001:5000 --restart=always --name registry registry:2 

docker build -t localhost:5001/lattice-api:monitor-test-v1 -f ../deploy/Dockerfile .

docker push localhost:5001/lattice-api:monitor-test-v1 

kubectl apply -f ./docker/deployment_eks.yaml  
```

## Tracking Historical Size for TrainingJobs
To enable tracking for historical size information, please install prometheus in the cluster:
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/prometheus -n lattice
```

Lattice-api-server will automatically be able to track historical size information.

## Developing

Load golang project and run `go build lattice-api-server`.

### Checks

Before filing a pull request, you should run checks locally by

```bash
make test # for unit tests and check style.
make lint # for golang lint.
```

## Troubleshooting

### Debugging Permission using Default Namespace

Ihe API server has a `default` namespace, for users from this namespace, the cluster may not have permission to call `list` for all job information.
Please apply this to enable the permission for debugging purpose,

```bash
 kubectl apply -f ./docker/fabric8-rbac.yaml
```

### Checking Logs

You can check the cluster application logs by 

```bash
kubectl logs deployment.apps/lattice-api-server
```


### Remote Cluster Deployment

- [ ] WIP

## Testing
### Deployment in the CI cluster
We have a Github Workflow that can build and apply the current lattice-api-server into the CI cluster managed by breezeml/operation.

To build and push the lattice-api-server to AWS ECR:
 - Click "Actions" for this repo
 - Choose the "ci" action
 - Click "Run workflow" and choose the branch you want to build
 - Select an action:
    * push-to-ecr: build and push lattice-api-server to AWS ECR
    * install-in-ci-cluster: install the lattice-api-server to the CI cluster
    * uninstall: uninstall the lattice-api-server from the CI cluster

