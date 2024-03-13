# Release

We release the lattice operator as a docker image. Before you get started, make sure you are using the right version number. If you need to change version number, update the `VERSION` file.

First, you need to build the docker image.

```bash
make docker-build
```

Next, you need to push the image to the repository. As we are using the jfrog docker repository which is private, you need to login first:

```bash
docker login breezeml.jfrog.io -u<username> -p<password>
```

Then, you can push the image:

```bash
make docker-push
```
