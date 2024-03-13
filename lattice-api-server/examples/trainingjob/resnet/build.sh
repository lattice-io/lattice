#!/bin/bash

cd $( dirname $0 )

VERSION=$( cat version )

# Prep data to include in image
python -c "import torchvision; torchvision.datasets.CIFAR10(root='./data', download=True)"

rm -f data/cifar-10-python.tar.gz

docker build . -t breezeml/lattice-resnet:$VERSION
