# backend/app/services/sms_service.py

from abc import ABC, abstractmethod
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


# ==========================================================
# 🔹 Base SMS Provider Interface
# ==========================================================
class BaseSMSProvider(ABC):

    @abstractmethod
    def send_sms(self, phone_number: str, message: str) -> None:
        pass


# ==========================================================
# 🔹 Console Provider (DEV MODE)
# ==========================================================
class ConsoleSMSProvider(BaseSMSProvider):

    def send_sms(self, phone_number: str, message: str) -> None:
        logger.info(f"[SMS DEBUG] To: {phone_number} | Message: {message}")


# ==========================================================
# 🔹 Future Twilio Provider (Template)
# ==========================================================
class TwilioSMSProvider(BaseSMSProvider):

    def send_sms(self, phone_number: str, message: str) -> None:
        # TODO: Implement actual Twilio integration
        raise NotImplementedError("Twilio integration not implemented yet")


# ==========================================================
# 🔹 Provider Factory
# ==========================================================
def get_sms_provider() -> BaseSMSProvider:

    if settings.DEBUG:
        return ConsoleSMSProvider()

    # Future: switch based on ENV
    # if settings.SMS_PROVIDER == "twilio":
    #     return TwilioSMSProvider()

    return ConsoleSMSProvider()