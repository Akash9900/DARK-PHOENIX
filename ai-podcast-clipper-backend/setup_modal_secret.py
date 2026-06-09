"""
Dark Phoenix - Modal Secret Setup Script
Run this script to create the required Modal secret.

Usage: python setup_modal_secret.py

This script reads credentials from environment variables (loaded from .env file)
instead of hardcoding them.
"""

import os
import modal
from dotenv import load_dotenv

# Load environment variables from the project-root .env file
load_dotenv("../.env")

# Create the secret with credentials from environment variables
secret = modal.Secret.from_dict({
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
    "AUTH_TOKEN": os.getenv("PROCESS_VIDEO_ENDPOINT_AUTH"),
    "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
    "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
    "AWS_REGION": os.getenv("AWS_REGION"),
    "S3_BUCKET_NAME": os.getenv("S3_BUCKET_NAME"),
    "MAX_CLIPS": os.getenv("MAX_CLIPS", "10")
})

print("Secret object created successfully!")
print("")
print("Loaded from environment variables:")
print(f"  - GEMINI_API_KEY: {'✓ Set' if os.getenv('GEMINI_API_KEY') else '✗ Missing'}")
print(f"  - AUTH_TOKEN: {'✓ Set' if os.getenv('PROCESS_VIDEO_ENDPOINT_AUTH') else '✗ Missing'}")
print(f"  - AWS_ACCESS_KEY_ID: {'✓ Set' if os.getenv('AWS_ACCESS_KEY_ID') else '✗ Missing'}")
print(f"  - AWS_SECRET_ACCESS_KEY: {'✓ Set' if os.getenv('AWS_SECRET_ACCESS_KEY') else '✗ Missing'}")
print(f"  - AWS_REGION: {'✓ Set' if os.getenv('AWS_REGION') else '✗ Missing'}")
print(f"  - S3_BUCKET_NAME: {'✓ Set' if os.getenv('S3_BUCKET_NAME') else '✗ Missing'}")
print(f"  - MAX_CLIPS: {os.getenv('MAX_CLIPS', '10')}")
print("")
print("To create a PERSISTENT secret, go to https://modal.com/secrets")
print("and create a secret named 'ai-podcast-clipper-secret' with these keys.")
