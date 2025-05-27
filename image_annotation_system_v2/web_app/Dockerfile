# Dockerfile for containerizing the web_app
# Details to be added later based on Python version and dependencies.

# Python base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set PYTHONPATH environment variable
ENV PYTHONPATH=/app

# Use wsgi.py as entry point
CMD gunicorn --bind "0.0.0.0:${PORT}" "wsgi:application"
