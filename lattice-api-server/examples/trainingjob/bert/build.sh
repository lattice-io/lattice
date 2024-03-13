#!/bin/bash

cd $( dirname $0 )

VERSION=$( cat version )

docker build . -t breezeml/lattice-bert:$VERSION
