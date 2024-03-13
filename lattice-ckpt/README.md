# Lattice Checkpoint Service

Lattice Checkpoint service provides a way to save and restore the model parameters, optimizer states, and other variables that are necessary to continue the training process.

## Build and run the service

Checkpoint service module is located at [src/ckpt_server/main.py](src/ckpt_server/main.py). You can use the [Dockerfile](Dockerfile) to build and run the checkpoint service:

- Build the docker image:

  ```
  docker build -t lattice-checkpoint-service .
  ```

- Run the service:

  ```
  docker run -p 5555:5555 lattice-checkpoint-service
  ```

Check the example provided at the [examples/client/client.py](examples/client/client.py) to see how to connect and work with the service.

## Release

If you make changes to the service module and you want to release, you have to build the docker image and pull it into the JFrog Artifactory. Here are the steps:

- Build the docker image:

  ```
  docker build -t lattice-checkpoint-service .
  ```
- Use the docker login command and provide your Artifactory username and password or API key:

  ```
  docker login breezeml.jfrog.io
  ```
- Tag with a proper `<VERSION>` and push the `lattice-checkpoint-service` image:

  ```
  docker tag lattice-checkpoint-service breezeml.jfrog.io/breezeml-docker-local/lattice-checkpoint-service:<VERSION>
  ```
  ```
  docker push breezeml.jfrog.io/breezeml-docker-local/lattice-checkpoint-service:<VERSION>
  ```

As we use Helm Charts for packaging the service, you have to modify `appVersion` in [helm/lattice-ckpt/Chart.yaml](helm/lattice-ckpt/Chart.yaml) in order to use the new docker image.
