# Playground Examples

For internal use only: This is a place to track the state of our playground examples.
Each example will have its source code as well as the Dockerfile used to create its image (and any additional
build scripts if necessary).

## Examples:
### Resnet
To use the Resnet example first go into the `resnet` directory.
Here you will find several things:
* Dockerfile
* build.sh
* job.yaml
* main.py

You should only interact with the `build.sh` for preparing the example.
This script will download the data to be used in the Docker container.
It will then run build and create an image called `breezeml/lattice-resnet`.
If you have access rights to the breezeml DockerHub repo, you can run
`docker push breezeml/lattice-resnet` to upload the docker image.

Next you can move on to testing.
As the data is packaged with the image, the only thing you should
have to do it run the yaml file with a cluster that has been configured
with the following things:
1. lattice-operator
2. lattice-ckpt
3. lattice-rdzv

`kubectl apply -f job.yaml`

### BERT
To use the BERT example first go into the `bert` directory.
Here you will find several things:
* Dockerfile
* build.sh
* job.yaml
* main.py

In order to make sure the data is cached so that it is ready to use,
you first need to run the `build.sh` script to build a base image.
Next you need to run the image and start the `main.py` file to download
the dataset and pre-process it.
Make sure to stop it shortly after you see that it is training (once
the data is finished processing):
```bash
docker run -it --gpus all breezeml/lattice-bert bash

torchrun main.py
```

You can run `torchrun main.py` several times to further reduce how long
it takes to load the dataset on startup (I am not sure why running it
several times reduces the load time, but it does...).
Finally, you can find the name of the docker and create a new commit
of that image:
```bash
docker ps -a # Get the name of the docker

docker commit <name> breezeml/lattice-bert
```

Now when you start the benchmark the next time, the data will be loaded
immediately, without having to download or process the dataset.
Next, you can upload to DockerHub using `docker push breezeml/lattice-bert`.

Next you can move on to testing.
As the data is packaged with the image, the only thing you should
have to do it run the yaml file with a cluster that has been configured
with the following things:
1. lattice-operator
2. lattice-ckpt
3. lattice-rdzv

`kubectl apply -f job.yaml`
