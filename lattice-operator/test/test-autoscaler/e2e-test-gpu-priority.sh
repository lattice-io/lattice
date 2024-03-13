#!/bin/bash

# helper function to check if the number of pod is correct
check_pod_number () {
    local job=$1
    local num=$2

    # Get the names of all pods in the lattice namespace
    local pod_names=$(kubectl --context=kwok-fake-cluster get pods --output=jsonpath='{.items..metadata.name}' -n lattice)
    
    # Count the number of pods for the job
    local job_pod_count=0
    for pod_name in $pod_names; do
    if [[ $pod_name == $job* ]]; then
        job_pod_count=$((job_pod_count + 1))
    fi
    done

    if [ $job_pod_count -eq $num ]; then
        return 0
    else
        return 1
    fi
}

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

passed=true
# ========================= TEST 1: create the first job =========================
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
check_pod_number "lattice-simple1" 4
if [ "$?" == 1 ]; then
    echo -e "\033[31mTest failed! Expected number of pods count is 4. \033[0m"
    passed=false
fi

# ========================= TEST 2: create the second job =========================
echo "Creating the second job with 2-4 pods..."
kubectl --context=kwok-fake-cluster apply -f test/test-autoscaler/jobs/trainingjob2_gpu.yaml

until [ $(kubectl --context=kwok-fake-cluster get trainingjob lattice-simple2 -n lattice --output=jsonpath='{@.status.stage}') = "Running" ]
do
    echo "Waiting for the job to run..."
    sleep 1
done

# Count the number of pods for the first job
check_pod_number "lattice-simple2" 2
if [ "$?" == 1 ]; then
    echo -e "\033[31mTest failed! Expected number of pods count is 2. \033[0m"
    passed=false
fi

# ========================= TEST 3: prioritize the second job =========================
echo "Increasing the priority of the second job..."
kubectl --context=kwok-fake-cluster patch trainingjob lattice-simple2 -n lattice --type=merge -p '{"spec":{"priority":1}}'
sleep 5

# Count the number of pods for the first job
check_pod_number "lattice-simple1" 0
if [ "$?" == 1 ]; then
    echo -e "\033[31mTest failed! Expected number of pods count is 0. \033[0m"
    passed=false
fi

# Count the number of pods for the second job
check_pod_number "lattice-simple2" 4
if [ "$?" == 1 ]; then
    echo -e "\033[31mTest failed! Expected number of pods count is 4. \033[0m"
    passed=false
fi


# ========================= TEST 4: deleting the second job =========================
echo "Deleting the first job..."
kubectl --context=kwok-fake-cluster delete -f test/test-autoscaler/jobs/trainingjob2_gpu.yaml
sleep 5

# Count the number of pods for the first job
check_pod_number "lattice-simple1" 4
if [ "$?" == 1 ]; then
    echo -e "\033[31mTest failed! Expected number of pods count is 4. \033[0m"
    passed=false
fi

# ========================= FINISH =========================
echo "Test ends, cleaning up..."
# Delete the job
kubectl --context=kwok-fake-cluster delete -f test/test-autoscaler/jobs/trainingjob1.yaml -n lattice

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
    echo -e "\033[31mTest failed!\033[0m"
    exit 1
fi
