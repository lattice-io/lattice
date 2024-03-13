# Releasing

Before you get started, make sure you have set the right chart version number in `Chart.yaml`

First, package the helm chart:

```bash
cd .. && helm package lattice-operator/
```

This command will generate a file `lattice-operator-<chart-version-number>.tgz`.

Lastly, you can upload this file to the Jfrog helm repo. You will need admin permission to do this.

```bash
curl -u<username>:<password> -T `lattice-operator-<chart-version-number>.tgz` "https://breezeml.jfrog.io/artifactory/breezeml-helm/lattice-operator-<chart-version-number>.tgz"
```
