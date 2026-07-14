import qrcode
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
QR_FOLDER = BASE_DIR / "static" / "qr_codes"

QR_FOLDER.mkdir(parents=True, exist_ok=True)


def generate_qr(slug: str) -> str:
    """
    Generate QR for user's public website.
    Returns public URL path.
    """

    website_url = f"https://apnamandla.in/{slug}"

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4,
    )

    qr.add_data(website_url)
    qr.make(fit=True)

    img = qr.make_image(fill="black", back_color="white")

    file_name = f"{slug}.png"
    file_path = QR_FOLDER / file_name

    img.save(file_path)

    # Public path (used in frontend)
    return f"/static/qr_codes/{file_name}"