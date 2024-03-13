#!/bin/bash

env

echo
echo "#########################################################"
echo "Running in a bash script -- No distributed env configured"

echo "MASTER_ADDR=$MASTER_ADDR"
echo "MASTER_PORT=$MASTER_PORT"
echo "MASTER_ADDR and MASTER_PORT should be empty"

echo "Done with bash script"
