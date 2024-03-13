#!/bin/bash

cd ../..

# Get manifests and kustomize
make manifests
make kustomize

# Get kwok
make kwok

# Start a fake cluster with a 5-GPU node
bin/kwokctl create cluster --name fake-cluster
kubectl --context=kwok-fake-cluster apply -f test/test-autoscaler/kwok/node-gpus.yaml

# Install the TrainingJob CRDs
bin/kustomize build manifests/base/crds | kubectl --context=kwok-fake-cluster apply -f -
sleep 10

# Create namespace
kubectl --context=kwok-fake-cluster create namespace lattice

# Run the operator and redirect the output, use gpu as the resource unit
RESOURCE_SCHEDULING_UNIT=nvidia.com/gpu KUBE_CONTEXT=kwok-fake-cluster go run cmd/training-operator.v1/main.go > /dev/null 2>&1 &

# Wait the operator to boost
sleep 5

echo "Creating the first job with 2-4 pods..."
kubectl --context=kwok-fake-cluster apply -f test/test-autoscaler/jobs/trainingjob1_gpu.yaml

until [ $(kubectl --context=kwok-fake-cluster get trainingjob lattice-simple1 -n lattice --output=jsonpath='{@.status.stage}') = "Running" ]
do
    echo "Waiting for the job to run..."
    sleep 1
done

# Get the names of all pods in the lattice namespace
pod_names=$(kubectl --context=kwok-fake-cluster get pods --output=jsonpath='{.items..metadata.name}' -n lattice)

# Count the number of pods for the first job
first_job_pod_count=0
for pod_name in $pod_names; do
  if [[ $pod_name == lattice-simple1* ]]; then
    first_job_pod_count=$((first_job_pod_count + 1))
  fi
done

passed=false
if [ $first_job_pod_count -eq 4 ]; then
  passed=true
else
  passed=false
fi

if [ "$passed" = false ]; then
  echo -e "\033[31mTest failed! Expected number of pods count is 4, but in fact got "$first_job_pod_count"\033[0m"
fi

echo "Creating the second job with 2-4 pods..."
kubectl --context=kwok-fake-cluster apply -f test/test-autoscaler/jobs/trainingjob2_gpu.yaml

until [ $(kubectl --context=kwok-fake-cluster get trainingjob lattice-simple2 -n lattice --output=jsonpath='{@.status.stage}') = "Running" ]
do
    echo "Waiting for the job to run..."
    sleep 1
done

# Get the names of all pods in the lattice namespace
pod_names=$(kubectl --context=kwok-fake-cluster get pods --output=jsonpath='{.items..metadata.name}' -n lattice)

# Count the number of pods for the second job
second_job_pod_count=0
for pod_name in $pod_names; do
  if [[ $pod_name == lattice-simple2* ]]; then
    second_job_pod_count=$((second_job_pod_count + 1))
  fi
done

passed=false
if [ $second_job_pod_count -eq 2 ]; then
  passed=true
else
  passed=false
fi

if [ "$passed" = false ]; then
  echo -e "\033[31mTest failed! Expected number of pods count is 2, but in fact got "$second_job_pod_count"\033[0m"
fi

# Delete the first job
echo "Deleting the first job..."
kubectl --context=kwok-fake-cluster delete -f test/test-autoscaler/jobs/trainingjob1_gpu.yaml
sleep 5

# Get the names of all pods in the lattice namespace
pod_names=$(kubectl --context=kwok-fake-cluster get pods --output=jsonpath='{.items..metadata.name}' -n lattice)

# Count the number of pods for the second job
second_job_pod_count=0
for pod_name in $pod_names; do
  if [[ $pod_name == lattice-simple2* ]]; then
    second_job_pod_count=$((second_job_pod_count + 1))
  fi
done

passed=false
if [ $second_job_pod_count -eq 4 ]; then
  passed=true
else
  passed=false
fi

if [ "$passed" = false ]; then
  echo -e "\033[31mTest failed! Expected number of pods count is 4, but in fact got "$second_job_pod_count"\033[0m"
fi

echo "Test ends, cleaning up..."
# Delete the job
kubectl --context=kwok-fake-cluster delete -f test/test-autoscaler/jobs/trainingjob2.yaml -n lattice

# Get the PPID of the go command
go_ppid=$(pgrep -f "go run cmd/training-operator.v1/main.go")

# Get the PID of the specific process using the PPID of the go command
operator_process_pid=$(ps -o pid= --ppid $go_ppid | tail -n 1)

# kill the operator
kill -9 $operator_process_pid
wait

# delete the test cluster
bin/kwokctl delete cluster --name fake-cluster

if [ "$passed" = true ]; then
  echo -e "\033[32mTest passed!\033[0m"
else
  echo -e "\033[31mTest failed! Expected number of pods count is 4, but in fact got "$first_job_pod_count"\033[0m"
  exit 1
fi
