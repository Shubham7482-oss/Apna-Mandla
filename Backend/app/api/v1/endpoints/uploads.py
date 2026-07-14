
from fastapi import APIRouter, File, UploadFile, Depends
from fastapi.responses import JSONResponse
import uuid

from app.utils.file_upload import save_upload_file, get_upload_path
from app.api import deps
from app import models

router = APIRouter()


@router.post("/uploads/image")
def upload_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(deps.get_current_active_user)
):
    """
    Upload an image.
    """
    # Generate a unique filename
    filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = get_upload_path(filename)

    save_upload_file(upload_file=file, destination=file_path)

    return JSONResponse(content={"image_url": file_path}, status_code=201)

