FROM public.ecr.aws/lambda/python:3.9-x86_64

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
COPY custom_exceptions.py ${LAMBDA_TASK_ROOT}/

# The WORKDIR and zip commands are not needed for container image deployment
# WORKDIR /var/task/package
# RUN zip -r /deployment_package.zip .

# Set the CMD to your handler
CMD ["lambda_function.lambda_handler"] 