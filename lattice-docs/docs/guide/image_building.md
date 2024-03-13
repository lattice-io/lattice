# Building an image to use with Lattice

In this tutorial, we will show you how to use a custom Docker image to run a PyTorch training job that uses Distributed Data Parallel (DDP) on Kubernetes. DDP is a PyTorch module that enables efficient parallelization of deep learning models across multiple GPUs.

## Prerequisites

* Running kubernetes cluster
* [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/) >= 1.23
* [docker CLI tools ](https://docs.docker.com/get-docker/)
* [DockerHub](https://hub.docker.com/) account (or other image hosting service)

## Preparing the training script

Before we can build our Docker image, we need to create a PyTorch training script that uses DDP. Here is an example script:
```python
import os

import torch
import torch.distributed as dist

# Initialize the distributed backend
# We set the following environment variables at runtime
# which configure the distributed environment:
#   RANK
#   LOCAL_RANK
#   WORLD_SIZE
#   MASTER_ADDR
#   MASTER_PORT
dist.init_process_group("nccl")

# Select which GPU device to use
torch.cuda.set_device(int(os.environ['LOCAL_RANK']))

# Define your model and optimizer
model = ...
optimizer = ...

# Wrap your model with DistributedDataParallel
model = torch.nn.parallel.DistributedDataParallel(model)

# Train your model
for epoch in range(num_epochs):
    for input, labels in data_loader:
        input = input.cuda()
        # Forward pass
        loss = model()

        # Backward pass
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

# Clean up the distributed backend
dist.destroy_process_group()
```

In this script, we first initialize the distributed backend using the NCCL backend, which is a backend used for distributed GPU training. We then define our model and optimizer, and wrap our model with `DistributedDataParallel`. Finally, we train our model using the wrapped model and optimizer.

Also as shown here, we have to configure our distributed environment using some environment variables.
These can be configured by using some wrapper process, such as the Lattice Agent to configure the job
correctly before running.

## Building the image

Next, we need to build a Docker image that includes our training script and any necessary dependencies. Here is an example `Dockerfile`:
```
FROM pytorch/pytorch:latest

# Install any additional dependencies
RUN pip install ...

# Copy the training script into the container
COPY train.py .
```

In this Dockerfile, we start with the latest PyTorch image as our base image. We then install any additional dependencies using pip, copy our training script into the container.

Once we've done this, we can create the image:
```
docker build . -t <my_image_name>
```

Run the following command to ensure the image was created and you should see it listed.
```
docker image ls
```

Make sure to note the image name for the next step.

## Deploying the image to a container registry

There a few steps to take here.
1. Make sure you have access to some container registry (DockerHub, JFrog, AWS ECR, etc)
2. On the image hosting service of your choice, create a repository for your image
3. Configure your build environment to access the repository
4. Push the container

** 1. Create an account **
We will walk through some of these steps here, using [DockerHub](https://hub.docker.com/) as an example.
First, make sure you have an account.

** 2. Create an image repository **
Once you are logged in, click on the "Repositories" tab and then click "Create repository".
Give the image repository a name and then press "Create".

In our example, let's assume that the our organization (or username) is `myorg` and the image
repository name we created is `my_image`.

** 3. Configure your build environment **
Once you have created the image repository, make sure that you can login.
On your build machine, run `docker login` and follow the instructions on the command line for access
to DockerHub.
For other hosting services (JFrog, AWS ECR, etc) you may have to specify the domain.
For example, for JFrog you would run `docker login myorg.jfrog.io`, whereas for AWS ECR you have to
login through the `aws` CLI tool.

** 4. Pushing the container **
Finally, with access properly configured, you can now do the following:

First, tag your image appropriately. Following our example above with `myorg`, we would run the
command
```
docker tag <my_image_name> myorg/my_image:<image_version>
```

Then, we can run
```
docker push myorg/my_image:<image_version>
```
to push the image to repository.
With a larger image, such as GPU based images which include CUDA, this can take some time.

## Using the image in a job

Before moving on, we need to configure our kubernetes cluster to have access rights
to our repository.
To do this, we need to create an image pull secret in our kubernetes cluster so that
it can access our private image.
```
kubectl create secret docker-registry my-dockerhub-secret
    --docker-server=docker.io
    --docker-username=<your DockerHub username>
    --docker-password=<your DockerHub password>
    --docker-email=<your DockerHub email>
```

Now we can return to the Kubernetes job submission seen in the overview and change it
to use our custom image.
The main changes we need to make are to change the name of the image to point to
the newly created repository and to specify the image pull secrets to use when
pulling the image.

```yaml
apiVersion: "breezeml.ai/v1"
kind: TrainingJob
metadata:
  name: example-job
  namespace: lattice
spec:
  minSize: 1
  maxSize: 3
  replicaSpecs:
    template:
      spec:
        imagePullSecrets:
          - name: my-dockerhub-secret
        containers:
          - name: trainingjob
            image: myorg/my_image:<version>
            imagePullPolicy: Always
            command: ["python", "-u", "train.py"]
```

Now when we run our job, Kubernetes will check the image pull secrets and download
the image from the repository.

Congratulations! Your custom training job is now running!
