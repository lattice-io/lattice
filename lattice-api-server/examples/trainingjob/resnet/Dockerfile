FROM python:3.8-slim
SHELL ["/bin/bash", "-c"]

WORKDIR /workspace

COPY data/ ./data/

COPY main.py .

RUN pip install torch==1.10.0+cpu torchvision==0.11.0+cpu -f https://download.pytorch.org/whl/torch_stable.html
RUN pip install boto3
