FROM python:3.7.16-slim

WORKDIR /workspace

COPY client.py ./

RUN pip install dill pyzmq numpy

# install torch cpu version to make the image smaller
RUN pip install torch --extra-index-url https://download.pytorch.org/whl/cpu