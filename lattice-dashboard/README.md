# Lattice Dashboard

## ✨ Features

- 🛠 [TypeScript](https://github.com/microsoft/TypeScript) + [ESLint](https://github.com/eslint/eslint) + [Prettier](https://github.com/prettier/prettier) + [lint-staged](https://github.com/okonet/lint-staged), preset configurations
- ❤️ [Less](https://github.com/less/less.js) + [Windi CSS](https://github.com/windicss/windicss), enjoyable CSS development experience
- ⚙️ Preset Vite plugins reasonable, pursue the ultimate development experience
- 💡 Fully features of [Ant Design](https://github.com/ant-design/ant-design), support style import on demand
- 💎 Provide different degrees of custom scaffolding, free choice, easy to use

## Quick Start

To start a developing server:

```bash
yarn && yarn dev
```

## Test Locally

To test the Lattice dashboard locally, you need to

1. Install [Minikube](https://minikube.sigs.k8s.io/docs/start/) and start a cluster locally.
2. Make sure [Lattice Operator](https://github.com/breezeml/lattice-operator) (latest version) is installed on the cluster.
3. Start [Lattice API Server](https://github.com/breezeml/lattice-api-server) from source by entering the project root and execute `NAMESPACE=lattice API_GROUP=breezeml.ai API_VERSION=v1 IN_CLUSTER=false go run main.go`.
4. Start the [Lattice Dashboard](https://github.com/breezeml/lattice-dashboard) locally by entering the project root and execute `yarn && yarn start`.
5. Modify the [api.ts](https://github.com/breezeml/lattice-dashboard/blob/1efe32eee53337142a287403bc9e58feb9e1cafb/config/apis.ts#L4) from `/api` to `http://localhost:8080/api` for local testing.
6. Setup Prometheus (to enable time-series worker data):

```
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prometheus prometheus-community/prometheus -n lattice
```

Port forward prometheus:

```
kubectl port-forward services/prometheus-server 9000:80 -n lattice
```

Also, please add PROMETHEUS_ENDPOINT="localhost:9000" as an environment variable at this line.

## Deployment

Build docker image

```
make docker-build
```

Test docker image

```bash
make docker-run
```

Push to the remote repo

```bash
make docker-push
```
