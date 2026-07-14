from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from app.utils.uploads import save_upload_file
from app.core.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/upload", tags=["Uploads"])

@router.post("/shop-image")
async def upload_shop_image(
    file: UploadFile = File(...), 
    current_user: User = Depends(get_current_user)
):
    # Check file type (sirf images allow karein)
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(400, "Sirf JPG, PNG ya WEBP images allowed hain.")

    # File size check (e.g., max 5MB)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > 5 * 1024 * 1024:
        raise HTTPException(400, "File size 5MB se zyada nahi honi chahiye.")

    # Save karein
    path = save_upload_file(file, sub_folder="shops")
    
    return {"image_url": path}