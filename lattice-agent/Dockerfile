FROM python:3.7.16

RUN apt update && apt install -y etcd

WORKDIR /workspace

COPY . ./

RUN pip install -r requirements/dev.txt
RUN pip install -r requirements/common.txt

RUN pip install --editable .

