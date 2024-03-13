# Lattice API Server

**Helm Version 0.0.10, App Version 0.2.8**

Lattice API Server provides RESTful APIs for Lattice Operator. It can be used by Frontend to manage Lattice jobs.

## Prerequisites

- Kubernetes >= v1.22
- Helm >= 3.8

We assume that there is already an existing K8s cluster accessible using "kubectl". You will also need a JFrog account that has read-access to breezeml.jfrog.io. If
not, please consult release administrators of BreezeML Inc.

## Installation

### Install from breezeml helm chart repo

Before you get started, please consult release administrators for your JFrog username and password.

First, add the breezeml repo.

```sh
helm repo add breezeml https://breezeml.jfrog.io/artifactory/api/helm/breezeml-helm \
  --username <jfrog_username> --password <jfrog_password>
```

Then, you can install the chart with the release name `lattice-api-server` in namespace `lattice`:

Please make sure your local chart repo is up-to-date:

```sh
helm repo update
```

```sh
helm install lattice-api-server breezeml/lattice-api-server \
  --namespace lattice \
  --set jfrog.username=<username> \
  --set jfrog.password=<password>
```

To get the status of the deployment, run:

```sh
kubectl get deployment lattice-api-server --namespace lattice
```
