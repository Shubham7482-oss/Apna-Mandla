
from sqlalchemy.orm import Session
from app.models.setting import Setting
from typing import Any, Dict


def get_setting(db: Session, key: str) -> Any:
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else None

def create_or_update_setting(db: Session, key: str, value: Any):
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting
