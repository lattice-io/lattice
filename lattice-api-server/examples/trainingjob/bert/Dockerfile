FROM python:3.8-slim

WORKDIR /workspace
RUN pip install torch==1.10.0 datasets transformers evaluate scikit-learn boto3

COPY main.py ./
