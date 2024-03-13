# Checkpoint Service Helm Chart

## Installation

### Install from breezeml helm chart repo

To work with Helm repositories, first install and configure your Helm client.

```sh
helm repo add breezeml-helm https://breezeml.jfrog.io/artifactory/api/helm/breezeml-helm \ 
--username <jfrog_username> --password <jfrog_password>
```

Then, you can install the chart with the release name `lattice-ckpt` in namespace `lattice`:

```sh
helm install lattice-ckpt breezeml/lattice-ckpt --namespace lattice --create-namespace \
  --set jfrog.username=<jfrog_username> \
  --set jfrog.password=<jfrog_password>
```

If you have the credentials as a `secret` object, you can use `--set imagePullSecretName=<secret-name>` to install the chart helm too.

The name of the checkpoint service is `lattice-checkpoint-svc` by default. You can change the service name using `--set service.name=<service-name>` during the the installation.

To get the status of the deployment, run:

```sh
kubectl get deployment lattice-ckpt --namespace lattice
```