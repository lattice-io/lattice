# Lattice Rendezvous

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

Lattice Rendezvous is a centralized storage service for multiple distributed workers to "meet" and synchronize. It is backed by a reliable and distributed store, such as etcd. In our current design of Lattice, the Lattice Rendezvous is used for Lattice Agents to share information for their corresponding jobs.

## Prerequisites

- Kubernetes >= v1.18
- Helm >= 3.8

## Install Lattice Rendezvous

### Install from breezeml helm chart repo

Before you get started, please consult release administrators for your repo username and password.

First, add the breezeml repo.

```sh
helm repo add breezeml https://breezeml.jfrog.io/artifactory/api/helm/breezeml-helm \
  --username <username> --password <password>
```

Then, install the chart with the release name `rdzv` in namespace `lattice`:

```sh
helm install rdzv breezeml/lattice-rdzv --namespace lattice --create-namespace
```

To get the status of the deployment, run:

```sh
kubectl get deployment lattice-rdzv --namespace lattice
```

### Install locally

First, clone the repo:

```sh
git clone git@github.com:breezeml/lattice-rdzv.git
```

Then install the chart:

```sh
cd helm/lattice-rdzv
helm install rdzv . --namespace lattice --create-namespace
```

### Installation configuration

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` |  |
| clientService.externalPort | int | `2379` |  |
| clientService.internalPort | int | `2379` |  |
| clientService.name | string | `"lattice-rdzv-client"` |  |
| clientService.type | string | `"ClusterIP"` |  |
| image | string | `"quay.io/coreos/etcd:v3.5.5"` |  |
| imagePullPolicy | string | `"IfNotPresent"` |  |
| nodeSelector | object | `{}` |  |
| rendezvous.backend | string | `"etcd"` |  |
| replicaCount | int | `1` |  |
| resources | object | `{}` |  |
| serverService.clientPort.externalPort | int | `2379` |  |
| serverService.clientPort.internalPort | int | `2379` |  |
| serverService.name | string | `"lattice-rdzv-server"` |  |
| serverService.serverPort.externalPort | int | `2380` |  |
| serverService.serverPort.internalPort | int | `2380` |  |
| serverService.type | string | `"ClusterIP"` |  |

For the default values of these configurations, please see `values.yaml`. If you want to change some of them, create a separate value file with only the properties you wish to update, and use '--values'/'-f' flag to install the chart. For more information, see [Values Files](https://helm.sh/docs/chart_template_guide/values_files/).

### Assigning pod to a specific node

You can use `nodeSelector` to specify the nodes with matching labels. For example, on AWS EKS, all nodes will have a label with the key `eks.amazonaws.com/nodegroup`, and these nodes in the same node group will have the same value. If you want to let rendezvous pods run on nodes inside a specific node group, for example, `Group1`, in your `myvalues.yaml`, add:

```yaml
nodeSelector:
  eks.amazonaws.com/nodegroup: Group1
```

## Uninstall Lattice Rendezvous

Uninstall the chart with the release name `rdzv` in namespace `lattice`:

```sh
helm uninstall rdzv --namespace lattice
```

## Use Lattice Rendezvous

Lattice Rendezvous is designed to be used by the Lattice Agents, which will try to access the rendezvous service through environment variables, including:

- `LATTICE_RDZV_CLIENT_SERVICE_HOST`
- `LATTICE_RDZV_CLIENT_SERVICE_PORT`
- `LATTICE_RDZV_BACKEND` (from the configmap lattice-rdzv-config)
