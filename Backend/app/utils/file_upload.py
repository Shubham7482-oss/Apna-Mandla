
import os
import shutil
from fastapi import UploadFile
from typing import IO

UPLOAD_DIR = "/static/uploads/"

def save_upload_file(upload_file: UploadFile, destination: str) -> str:
    """
    Saves an uploaded file to the specified destination.

    Args:
        upload_file: The uploaded file.
        destination: The path to save the file to.

    Returns:
        The path to the saved file.
    """
    try:
        with open(destination, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
    finally:
        upload_file.file.close()
    return destination


def get_upload_path(filename: str) -> str:
    """
    Returns the full path to an uploaded file.

    Args:
        filename: The name of the file.

    Returns:
        The full path to the file.
    """
    return os.path.join(UPLOAD_DIR, filename)

