# Lattice Operator

Lattice Operator is a Kubernetes operator that uses custom resources to manage ML jobs. 
It includes a set of Kubernetes CRDs, such as TrainingJob for distributed ML training jobs.

In this document, we describe how to deploy Lattice Operator in your existing K8s cluster.

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

Then, you can install the chart with the release name `operator` in namespace `lattice`:

Please make sure your local chart repo is up-to-date:
```sh
helm repo update
```

```sh
# you don't have to encode your <jfrog_username> and <jfrog_password> in this command
helm install operator breezeml/lattice-operator --namespace lattice --create-namespace \
  --set jfrog.username=<jfrog_username> \
  --set jfrog.password=<jfrog_password> \
  --set license=<your_license_key>
```

To get the status of the deployment, run:

```sh
kubectl get deployment lattice-operator --namespace lattice
```

### Installation configuration

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` |  |
| group | string | `"breezeml.ai"` | Group name of the operator |
| image | string | `"breezeml.jfrog.io/breezeml-docker/lattice-operator"` | Docker image of the operator. Only modify it when running from docker images built locally. |
| imagePullPolicy | string | `"IfNotPresent"` |  |
| monitorNamespace | string | `""` |  |
| nodeSelector | object | `{}` | Selector that can specify in which nodes the operator pod should be deployed |
| replicaCount | int | `1` |  |
| resources.limits.cpu | string | `"100m"` |  |
| resources.limits.memory | string | `"128Mi"` |  |
| resources.requests.cpu | string | `"100m"` |  |
| resources.requests.memory | string | `"128Mi"` |  |
| service.enablePrometheus | bool | `false` |  |
| service.externalPort | int | `8080` |  |
| service.internalPort | int | `8080` |  |
| service.probePort | int | `8081` |  |
| service.type | string | `"ClusterIP"` |  |
| terminationGracePeriodSeconds | int | `10` |  |
| jfrog.secretName | string | jfrogsecret | No need to modify unless you have a secret with the same name. |
| jfrog.dockerSecretName | string | dockersecret | No need to modify unless you have a secret with the same name. |
| jfrog.username | string | Your user name in JFrog (no need to encode) |
| jfrog.password | string | Your password in JFrog (no need to encode) |
| license | string | Your license key issued by us |

For the default values of these configurations, please see `values.yaml`. If you want to change some of them, create a separate value file with only the properties you wish to update, and use '--values'/'-f' flag to install the chart. For more information, see [Values Files](https://helm.sh/docs/chart_template_guide/values_files/).

### Assigning pod to a specific node

You can use `nodeSelector` to specify the nodes with matching labels. For example, on AWS EKS, all nodes will have a label with the key `eks.amazonaws.com/nodegroup`, and these nodes in the same node group will have the same value. If you want to let rendezvous pods run on nodes inside a specific node group, for example, `Group1`, in your `values.yaml`, add:

```yaml
nodeSelector:
  eks.amazonaws.com/nodegroup: Group1
```

## Cleanup

Uninstall the chart with the release name `operator` in namespace `lattice`:

```sh
helm uninstall operator --namespace lattice
```

# API Reference

Lattice-operator manages machine learning training jobs through a "TrainingJob" CRD.

## Example TrainingJob yaml file
```yaml
apiVersion: "breezeml.ai/v1"
kind: TrainingJob
metadata:
  name: lattice-simple1
  namespace: lattice
spec:
  runPolicy:
    cleanPodPolicy: "All"
  minSize: 2
  maxSize: 4
  priority: 0
  injectLattice: true
  replicaSpecs:
    template:
      spec:
        containers:
          - name: trainingjob
            image: breezeml/lattice-resnet:1.0.1
            imagePullPolicy: Always
            command:
              - python
            args: ["-u", "main.py"]
            resources:
              requests:
                nvidia.com/gpu: 1
              limits:
                nvidia.com/gpu: 1
```

## Packages
- [breezeml.ai/v1](#breezemlaiv1)


## breezeml.ai/v1

Package v1 is the v1 version of the API.

Package v1 contains API Schema definitions for the breezeml.ai v1 API group



#### TrainingJob



TrainingJob is the Schema for the trainingjobs API

_Appears in:_
- [TrainingJobList](#trainingjoblist)

| Field | Description |
| --- | --- |
| `TypeMeta` _[TypeMeta](https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.22/#typemeta-v1-meta)_ |  |
| `metadata` _[ObjectMeta](https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.22/#objectmeta-v1-meta)_ | Refer to Kubernetes API documentation for fields of `metadata`. |
| `spec` _[TrainingJobSpec](#trainingjobspec)_ |  |
| `status` _[TrainingJobStatus](#trainingjobstatus)_ |  |




#### TrainingJobSpec



TrainingJobSpec defines the desired state of TrainingJob

_Appears in:_
- [TrainingJob](#trainingjob)

| Field | Description |
| --- | --- |
| `runPolicy` _[RunPolicy](#runpolicy)_ | RunPolicy encapsulates various runtime policies of the distributed training job, for example, how to clean up resources and how long the job can stay active. |
| `replicaSpecs` _ReplicaSpec_ | ReplicaSpec (value). Specifies configuration for containers. It no longer handles the number of nodes. The lattice operator will generate replica numbers dynamically |
| `minSize` _integer_ | The following two parameters configure elastic behavior of the job. We only consider running the job with [MinSize, MaxSize] nodes. If unspecified, they are set to [1,1] |
| `maxSize` _integer_ |  |
| `injectLattice` _boolean_ | We use this part of the spec as a way to determine whether we should inject the Lattice Agent and Lattice Addons using the Lattice Installer. Currently, enabling this imposes the requirement that the container used must have python and pip installed and MUST have an explicit command in the yaml file, not use the implicit command in the docker. If unspecified, set to false |
| `framework` _TrainingJobFramework_ | The framework of the TrainingJob Will be sent to agent as an ENV variable Default: pytorch |
| `priority` _integer_ | Priority of the job as an integer. A job with higher priority will always be scheduled first. A job with higher priority can take over resources from lower ones preemptively. Default: 0 |


#### TrainingJobStatus



TrainingJobStatus defines the observed state of TrainingJob

_Appears in:_
- [TrainingJob](#trainingjob)

| Field | Description |
| --- | --- |
| `execStatus` _[JobStatus](#jobstatus)_ | Note: execution status handles single-job scheduling information after the autoscaling algorithm has determined intended replicaSpecs for it. The reconciler will try to control the exec status to match the indended status determined by the autoscaler |
| `currentSize` _integer_ | CurrentSize: how many workers should a job run with; Stage: whether the job is waiting, running, or has finished. These are the *intended* status of the jobs. At runtime, we reconcile jobs to meet such status. |
| `stage` _TrainingJobStage_ |  |
| `submitTime` _[Time](https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.22/#time-v1-meta)_ | For autoscaling:   SubmitTime: the time when the job was submitted to the cluster.     Note - it is different from the StartTime in LagacyStatus. Submitted jobs might not be started. It is represented in RFC3339 form and is in UTC. |
| `queuedTime` _[Time](https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.22/#time-v1-meta)_ | For autoscaling:   QueuedTime: the time when the job was put into the waiting list/running list   By default it is the same as SubmitTime. However, if the job failed to be scheduled to specific nodes,   the value will be reset. We use this timestamp to allow FIFO. |
| `lastExecTime` _[Time](https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.22/#time-v1-meta)_ | Time when the job was last executed |
| `completionTime` _[Time](https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.22/#time-v1-meta)_ | Time when the job was completed |
| `requeueTime` _[Time](https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.22/#time-v1-meta)_ | Time when we want to remove the job from the running list if some pod is still pending Every time the autoscaler touches currentSize or Stage, we need to reset it to nil. We set this when we see some pod are seen pending for the first time. Nil by default |
| `cooldownTime` _[Time](https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.22/#time-v1-meta)_ | Time before which the trainingjob is on cooldown It is used when we decide to remove the schedule-failure job from the running list We only attempt to requeue the job once we pass the cooldown time Nil by default |
