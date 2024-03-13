#!/bin/bash

cd ../..

# Create a test namespace
kubectl create namespace lattice

# Install the CRD
make install 
wait

# Run the operator and redirect the output, DEBUG_WORLD_SIZE=5 is used to mock a 5-node cluster to the operator 
DEBUG_WORLD_SIZE=5 go run cmd/training-operator.v1/main.go > /dev/null 2>&1 &

# Wait the operator to boost
sleep 5

# Create a job with min_pod = 2, max_pod = 4 
echo "Creating the first job with 2-4 pods..."
kubectl apply -f test/test-autoscaler/jobs/trainingjob1.yaml -n lattice

# Wait the auto-scaler to scale the running job
sleep 40

# Get the names of all pods in the lattice namespace
pod_names=$(kubectl get pods --output=jsonpath='{.items..metadata.name}' -n lattice)

echo "Checking the number of pods..."

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

echo "Test ends, cleaning up..."

# Delete the job
kubectl delete -f test/test-autoscaler/jobs/trainingjob1.yaml -n lattice

# Get the PPID of the go command
go_ppid=$(pgrep -f "go run cmd/training-operator.v1/main.go")

# Get the PID of the specific process using the PPID of the go command
operator_process_pid=$(ps -o pid= --ppid $go_ppid | tail -n 1)

# kill the operator
kill -9 $operator_process_pid
wait

if [ "$passed" = true ]; then
  echo -e "\033[32mTest passed!\033[0m"
else
  echo -e "\033[31mTest failed! Expected number of pods count is 4, but in fact got "$first_job_pod_count"\033[0m"
  exit 1
fi