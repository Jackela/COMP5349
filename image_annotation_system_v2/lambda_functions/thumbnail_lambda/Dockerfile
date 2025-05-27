# 1. 使用官方的、架构明确的 AWS Lambda Python 3.9 基础镜像
FROM public.ecr.aws/lambda/python:3.9-x86_64

# Install OS-level dependencies if any (e.g., for Pillow or other libraries)
# RUN yum install -y some-package

# 2. 将依赖需求文件复制到工作目录
COPY requirements.txt .

# 3. 关键修复：使用精确的平台和版本标志，强制pip下载兼容的二进制包
RUN pip install -r requirements.txt

# 4. 将我们的函数代码也复制到 "package" 目录中
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
COPY custom_exceptions.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler (could also be done in CloudFormation)
CMD ["lambda_function.lambda_handler"] 