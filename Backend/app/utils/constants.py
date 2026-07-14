# app/utils/constants.py

"""
System-wide constants for Apna Mandla.

Keep only:
- enums
- fixed system values
- shared labels

Do NOT keep:
- secrets
- environment-dependent values
"""

# ───────────────────────────────
# USER TYPES
# ───────────────────────────────
USER_TYPE_CUSTOMER = "CUSTOMER"
USER_TYPE_RIDER = "RIDER"
USER_TYPE_SHOP = "SHOP"
USER_TYPE_GOVT = "GOVT"
USER_TYPE_ADMIN = "ADMIN"

# ───────────────────────────────
# AVAILABILITY STATUSES
# ───────────────────────────────
STATUS_AVAILABLE = "AVAILABLE"
STATUS_BUSY = "BUSY"
STATUS_CLOSED = "CLOSED"

# ───────────────────────────────
# APPROVAL STATUSES
# ───────────────────────────────
APPROVAL_PENDING = "PENDING"
APPROVAL_APPROVED = "APPROVED"
APPROVAL_REJECTED = "REJECTED"

# ───────────────────────────────
# ORDER PREFIXES
# ───────────────────────────────
ORDER_PREFIX = "ORD"
RIDER_PREFIX = "RID"
SHOP_PREFIX = "SHP"
