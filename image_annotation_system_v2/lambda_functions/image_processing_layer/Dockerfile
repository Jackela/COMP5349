FROM public.ecr.aws/lambda/python:3.9-x86_64

RUN yum install -y zip

COPY requirements.txt .

RUN pip install \
    --platform manylinux2014_x86_64 \
    --target="./python" \
    --implementation cp \
    --python-version 3.9 \
    --only-binary=:all: \
    -r requirements.txt

RUN zip -r /deployment_package.zip ./python 