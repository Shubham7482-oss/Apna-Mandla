"""
app/utils/fcm.py

Firebase Cloud Messaging helper.

Credential loading priority:
  1. FIREBASE_CREDENTIALS_JSON env var — full JSON string (recommended for
     containers and cloud environments where secrets are injected as env vars).
  2. FIREBASE_CREDENTIALS_PATH env var — path to a local JSON file (suitable
     for local development only).

NEVER commit firebase-credentials.json to source control.
Add it to .gitignore and use a secrets manager or env var in production.

Initialisation is lazy: the Admin SDK is only initialised on the first call
to send_fcm_notification(), so import-time failures do not crash the app.
"""

import json
import logging
import os

import firebase_admin
from firebase_admin import credentials, messaging

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# LAZY INITIALISATION
# ─────────────────────────────────────────────────────────────────────────────

def _init_firebase() -> bool:
    """
    Initialise the Firebase Admin SDK if not already done.

    Returns True on success, False if credentials are not configured.
    Logs errors but does not raise — a missing Firebase config should degrade
    gracefully (notifications are not delivered) rather than crash the API.
    """
    if firebase_admin._apps:
        return True  # already initialised

    try:
        if settings.FIREBASE_CREDENTIALS_JSON:
            # Production path: credentials injected as an env-var JSON string.
            # Example setup:
            #   export FIREBASE_CREDENTIALS_JSON="$(cat firebase-credentials.json)"
            cred_dict = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
            cred = credentials.Certificate(cred_dict)
            logger.info("Firebase Admin SDK initialised from FIREBASE_CREDENTIALS_JSON.")

        elif os.path.isfile(settings.FIREBASE_CREDENTIALS_PATH):
            # Development path: credentials read from a local file.
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            logger.info(
                "Firebase Admin SDK initialised from file: %s",
                settings.FIREBASE_CREDENTIALS_PATH,
            )

        else:
            logger.warning(
                "Firebase credentials not configured. "
                "Set FIREBASE_CREDENTIALS_JSON or FIREBASE_CREDENTIALS_PATH. "
                "Push notifications will be disabled."
            )
            return False

        firebase_admin.initialize_app(cred)
        return True

    except json.JSONDecodeError as exc:
        logger.error("FIREBASE_CREDENTIALS_JSON is not valid JSON: %s", exc)
        return False
    except Exception as exc:
        logger.error("Firebase Admin SDK initialisation failed: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def send_fcm_notification(
    device_token: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> bool:
    """
    Send a push notification to a single device via FCM.

    Args:
        device_token: The FCM registration token for the target device.
        title:        Notification title (shown in the system tray).
        body:         Notification body text.
        data:         Optional key-value data payload (all values must be str).

    Returns:
        True if the message was accepted by FCM, False otherwise.
    """
    if not _init_firebase():
        logger.warning(
            "FCM not initialised — skipping notification to %s…%s",
            device_token[:6],
            device_token[-4:],
        )
        return False

    # Ensure all data values are strings (FCM requirement).
    safe_data = {k: str(v) for k, v in (data or {}).items()}

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        token=device_token,
        data=safe_data,
    )

    try:
        response = messaging.send(message)
        logger.debug("FCM message sent: %s", response)
        return True
    except messaging.UnregisteredError:
        # Token is no longer valid — caller should remove it from the DB.
        logger.warning("FCM device token is no longer registered: %s…%s", device_token[:6], device_token[-4:])
        return False
    except Exception as exc:
        logger.error("FCM send failed: %s", exc)
        return False
