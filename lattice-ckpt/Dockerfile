# Use an official Python runtime as a parent image
FROM python:3-alpine

# set the working directory in the container
WORKDIR /usr/ckpt-service/

# copy the dependencies file to the working directory
COPY requirements.txt ./

# install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# copy the content of the local src directory to the working directory
COPY ./src/ .

# command to run the checkpoint service on container start
CMD [ "python", "ckpt_server/main.py", "--root-dir", "/ckpt_root" ]

