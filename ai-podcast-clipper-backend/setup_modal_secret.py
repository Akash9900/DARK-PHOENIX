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
    "MAX_CLIPS": os.getenv("MAX_CLIPS", "10"),
    "WATERMARK_ENABLED": os.getenv("WATERMARK_ENABLED", "false"),
    "WATERMARK_TEXT": os.getenv("WATERMARK_TEXT", "LUNARTECH.AI"),
    "WATERMARK_POSITION": os.getenv("WATERMARK_POSITION", "lower-right"),
    "WATERMARK_OPACITY": os.getenv("WATERMARK_OPACITY", "0.7"),
    "WATERMARK_FONT_SIZE": os.getenv("WATERMARK_FONT_SIZE", "30"),
    "WATERMARK_IMAGE_ENABLED": os.getenv("WATERMARK_IMAGE_ENABLED", "false"),
    "WATERMARK_IMAGE_PATH": os.getenv("WATERMARK_IMAGE_PATH", "assets/watermark.png"),
    "WATERMARK_IMAGE_SCALE": os.getenv("WATERMARK_IMAGE_SCALE", "0.1"),
    "GOOGLE_DRIVE_CREDENTIALS_JSON": os.getenv("GOOGLE_DRIVE_CREDENTIALS_JSON"),
    "GOOGLE_DRIVE_ENABLED": os.getenv("GOOGLE_DRIVE_ENABLED", "false"),
    "GOOGLE_DRIVE_FOLDER_ID": os.getenv("GOOGLE_DRIVE_FOLDER_ID")
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
print(f"  - WATERMARK_ENABLED: {os.getenv('WATERMARK_ENABLED', 'false')}")
print(f"  - WATERMARK_TEXT: {os.getenv('WATERMARK_TEXT', 'LUNARTECH.AI')}")
print(f"  - WATERMARK_POSITION: {os.getenv('WATERMARK_POSITION', 'lower-right')}")
print(f"  - WATERMARK_OPACITY: {os.getenv('WATERMARK_OPACITY', '0.7')}")
print(f"  - WATERMARK_FONT_SIZE: {os.getenv('WATERMARK_FONT_SIZE', '30')}")
print(f"  - WATERMARK_IMAGE_ENABLED: {os.getenv('WATERMARK_IMAGE_ENABLED', 'false')}")
print(f"  - WATERMARK_IMAGE_PATH: {os.getenv('WATERMARK_IMAGE_PATH', 'assets/watermark.png')}")
print(f"  - WATERMARK_IMAGE_SCALE: {os.getenv('WATERMARK_IMAGE_SCALE', '0.1')}")
print(f"  - GOOGLE_DRIVE_CREDENTIALS_JSON: {'✓ Set' if os.getenv('GOOGLE_DRIVE_CREDENTIALS_JSON') else '✗ Missing'}")
print(f"  - GOOGLE_DRIVE_ENABLED: {os.getenv('GOOGLE_DRIVE_ENABLED', 'false')}")
print(f"  - GOOGLE_DRIVE_FOLDER_ID: {'✓ Set' if os.getenv('GOOGLE_DRIVE_FOLDER_ID') else '✗ Missing'}")
print("")
print("To create a PERSISTENT secret, go to https://modal.com/secrets")
print("and create a secret named 'ai-podcast-clipper-secret' with these keys.")

# Note: INNGEST_SIGNING_KEY and INNGEST_EVENT_KEY are NOT added to the Modal secret.
# They must be set in Vercel environment variables directly (the Inngest SDK reads
# them from process.env).
