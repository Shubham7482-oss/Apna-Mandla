
import os
import shutil
import uuid
from fastapi import UploadFile
from app.core.config import settings

UPLOAD_DIR = "backend/app/static/uploads"

def save_upload_file(upload_file: UploadFile, sub_folder: str) -> str:
    try:
        # Create a unique filename
        file_extension = os.path.splitext(upload_file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # Create the destination path
        destination_folder = os.path.join(UPLOAD_DIR, sub_folder)
        os.makedirs(destination_folder, exist_ok=True)
        destination = os.path.join(destination_folder, unique_filename)

        with open(destination, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)

        # Return the relative path for URL generation
        return os.path.join("/static/uploads", sub_folder, unique_filename)

    finally:
        upload_file.file.close()

def get_image_url(file_path: str) -> str:
    # This assumes the app is hosted at the root.
    # In a production environment with a different base URL, you might need to adjust this.
    return file_path
