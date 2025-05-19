from setuptools import setup, find_packages

setup(
    name="image_annotation_system",
    version="0.1",
    packages=find_packages(include=["web_app", "web_app.*", "lambda_functions", "lambda_functions.*"]),
    install_requires=[
        "Flask==2.3.3",
        "Werkzeug==2.3.7",
        "Jinja2==3.1.2",
        "boto3==1.28.57",
        "mysql-connector-python==8.0.33",
        "python-dotenv==1.0.0",
        "gunicorn==21.2.0",
        "click==8.1.7",
        "itsdangerous==2.1.2",
        "MarkupSafe==2.1.3"
    ],
    python_requires=">=3.9",
    author="COMP5349 Student",
    description="Image Annotation System for COMP5349",
    keywords="image annotation, flask, aws",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.9",
    ],
)