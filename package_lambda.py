#!/usr/bin/env python3
"""
Lambda packaging utility for creating deployment packages
"""
import os
import sys
import shutil
import zipfile
import subprocess
import tempfile
from pathlib import Path

def create_lambda_package(lambda_dir, output_name):
    """Create a Lambda deployment package"""
    lambda_path = Path(lambda_dir)
    
    if not lambda_path.exists():
        print(f"Error: Lambda directory {lambda_dir} does not exist")
        return False
    
    print(f"Creating Lambda package for {lambda_dir}...")
    
    # Create temporary directory for packaging
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        package_path = temp_path / "package"
        package_path.mkdir()
        
        # Check for requirements.txt
        requirements_file = lambda_path / "requirements.txt"
        if requirements_file.exists():
            print("Installing dependencies...")
            # Install dependencies to package directory
            result = subprocess.run([
                sys.executable, "-m", "pip", "install",
                "-r", str(requirements_file),
                "-t", str(package_path),
                "--no-cache-dir"
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Error installing dependencies: {result.stderr}")
                return False
        
        # Copy lambda function code
        print("Copying function code...")
        for item in lambda_path.iterdir():
            if item.name in ['.git', '__pycache__', '.pytest_cache', 'package']:
                continue
            if item.is_file() and item.suffix == '.py':
                shutil.copy2(item, package_path)
            elif item.is_file() and item.name != 'requirements.txt':
                shutil.copy2(item, package_path)
        
        # Create zip file
        zip_path = lambda_path / output_name
        print(f"Creating zip file: {zip_path}")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(package_path):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(package_path)
                    zip_file.write(file_path, arcname)
        
        print(f"Lambda package created successfully: {zip_path}")
        return True

def main():
    # Package thumbnail_lambda
    thumbnail_dir = "lambda_functions/thumbnail_lambda"
    if not create_lambda_package(thumbnail_dir, "thumbnail_lambda.zip"):
        return 1
    
    # Package annotation_lambda
    annotation_dir = "lambda_functions/annotation_lambda"
    if not create_lambda_package(annotation_dir, "annotation_lambda.zip"):
        return 1
    
    print("\nAll Lambda packages created successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 