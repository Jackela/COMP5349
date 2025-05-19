# Dockerfile for containerizing the web_app
# Details to be added later based on Python version and dependencies.

# 1. Choose a Base Image
FROM python:3.9-slim-buster

# 2. Set Working Directory
WORKDIR /app

# 3. Set Environment Variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV PORT=5000

# 4. Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the application code
COPY . .

# 6. Expose the port the app runs on
EXPOSE ${PORT}

# 7. Define the command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:${PORT}", "app:app"] 