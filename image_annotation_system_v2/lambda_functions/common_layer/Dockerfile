# 1. 使用官方的、架构明确的 AWS Lambda Python 3.9 基础镜像
FROM public.ecr.aws/lambda/python:3.9-x86_64

# Install zip utility
RUN yum install -y zip

# 2. 将依赖需求文件复制到工作目录
COPY requirements.txt .

# 3. 关键修复：使用精确的平台和版本标志，强制pip下载兼容的二进制包
#    并将依赖安装到 python/ 目录下以符合Lambda Layer的结构
RUN pip install \
    --platform manylinux2014_x86_64 \
    --target="./python" \
    --implementation cp \
    --python-version 3.9 \
    --only-binary=:all: \
    -r requirements.txt

# 4. 将 "python" 目录（包含所有依赖）打包成zip文件
WORKDIR /var/task
RUN zip -r /deployment_package.zip ./python 