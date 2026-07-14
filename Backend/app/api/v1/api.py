from fastapi import APIRouter

from app.routes import (
    commission, marketplace, health, auth_login, auth_verify, admin_order, shop_profile,
    parcel, order_flow, admin_shop, ws, rider, discount, auth_signup, ads, admin_stats,
    mandla, rider_auth, uploads, admin_rider, rider_tasks, admin_subscription, notification,
    support, riders, shop, cart, admin_parcel, auth_otp, udhar, order_proofs,
    shop_registration, rating, rider_registration, users, shop_order, auth_password,
    order, auth_logout, auth_refresh, auth_sessions, wallets, kyc, admin_ledger, product,
    subscription, withdrawal, logistics, website, payment, admin_management, dashboard,
    admin_auth, auth_forgot, admin_finance, dispatch, rider_location, delivery, gateway,
)
from app.api.v1.endpoints.settings import router as settings_router

api_router = APIRouter()

# ── Health ────────────────────────────────────────────────────────────────────
api_router.include_router(health, tags=["Health"])

# ── Authentication ────────────────────────────────────────────────────────────
# All auth routers define NO prefix themselves.
# api.py is the single source of the /auth prefix.
# Final paths: /api/v1/auth/<endpoint>
api_router.include_router(auth_signup,   prefix="/auth", tags=["Authentication"])
api_router.include_router(auth_login,    prefix="/auth", tags=["Authentication"])
api_router.include_router(auth_verify,   prefix="/auth", tags=["Authentication"])
api_router.include_router(auth_otp,      prefix="/auth", tags=["Authentication"])
api_router.include_router(auth_password, prefix="/auth", tags=["Authentication"])
api_router.include_router(auth_forgot,   prefix="/auth", tags=["Authentication"])
api_router.include_router(auth_logout,   prefix="/auth", tags=["Authentication"])
api_router.include_router(auth_refresh,  prefix="/auth", tags=["Authentication"])
api_router.include_router(auth_sessions, prefix="/auth", tags=["Sessions"])

# ── Users ─────────────────────────────────────────────────────────────────────
# users router has NO prefix; api.py provides /users.
# Final path: /api/v1/users/me  (was /users/users/me — fixed)
api_router.include_router(users, prefix="/users", tags=["Users"])

# ── Shop ──────────────────────────────────────────────────────────────────────
api_router.include_router(shop,              prefix="/shop",              tags=["Shop"])
api_router.include_router(shop_registration, prefix="/shop-registration", tags=["Shop Registration"])
api_router.include_router(shop_profile,      prefix="/shop-profile",      tags=["Shop Profile"])
api_router.include_router(shop_order,        prefix="/shop-order",        tags=["Shop Order"])

# ── Commerce ──────────────────────────────────────────────────────────────────
api_router.include_router(product,     prefix="/products",    tags=["Products"])
api_router.include_router(cart,        prefix="/cart",        tags=["Cart"])
api_router.include_router(order,       prefix="/orders",      tags=["Orders"])
api_router.include_router(order_flow,  prefix="/order-flow",  tags=["Order Flow"])
api_router.include_router(order_proofs,prefix="/order-proofs",tags=["Order Proofs"])
api_router.include_router(payment,     prefix="/payment",     tags=["Payment"])
api_router.include_router(marketplace, prefix="/marketplace", tags=["Marketplace"])
api_router.include_router(dashboard,   prefix="/dashboard",   tags=["Dashboard"])
api_router.include_router(logistics,   prefix="/logistics",   tags=["Logistics"])
api_router.include_router(mandla,      prefix="/mandla",      tags=["Mandla"])

# ── Supporting features ───────────────────────────────────────────────────────
api_router.include_router(notification, prefix="/notification", tags=["Notification"])
api_router.include_router(rating,       prefix="/rating",       tags=["Rating"])
api_router.include_router(support,      prefix="/support",      tags=["Support"])
api_router.include_router(uploads,      prefix="/uploads",      tags=["Uploads"])
api_router.include_router(wallets,      prefix="/wallets",      tags=["Wallets"])
api_router.include_router(withdrawal,   prefix="/withdrawal",   tags=["Withdrawal"])
api_router.include_router(gateway,      prefix="/gateway",      tags=["Gateway"])
api_router.include_router(udhar,        prefix="/udhar",        tags=["Udhar"])
api_router.include_router(commission,   prefix="/commission",   tags=["Commission"])
api_router.include_router(subscription, prefix="/subscription", tags=["Subscription"])
api_router.include_router(ads,          prefix="/ads",          tags=["Ads"])
api_router.include_router(kyc,          prefix="/kyc",          tags=["KYC"])
api_router.include_router(website,      prefix="/website",      tags=["Website"])
api_router.include_router(discount,     prefix="/discount",     tags=["Discount"])

# ── Rider ─────────────────────────────────────────────────────────────────────
api_router.include_router(riders,            prefix="/riders",            tags=["Riders"])
api_router.include_router(rider,             prefix="/rider",             tags=["Rider"])
api_router.include_router(rider_auth,        prefix="/rider-auth",        tags=["Rider Authentication"])
api_router.include_router(rider_registration,prefix="/rider-registration",tags=["Rider Registration"])
api_router.include_router(rider_tasks,       prefix="/rider-tasks",       tags=["Rider Tasks"])
api_router.include_router(dispatch.router,   prefix="/dispatch",          tags=["Dispatch"])
api_router.include_router(rider_location.router, prefix="/rider-location",tags=["Rider Location"])
api_router.include_router(delivery.router,   prefix="/delivery",          tags=["Delivery"])

# ── WebSocket ─────────────────────────────────────────────────────────────────
api_router.include_router(ws, tags=["WebSocket"])

# ── Admin ─────────────────────────────────────────────────────────────────────
api_router.include_router(admin_auth,         prefix="/admin/auth",          tags=["Admin Authentication"])
api_router.include_router(admin_finance,       prefix="/admin/finance",       tags=["Admin Finance"])
api_router.include_router(admin_ledger,        prefix="/admin/ledger",        tags=["Admin Ledger"])
api_router.include_router(admin_management,    prefix="/admin/management",    tags=["Admin Management"])
api_router.include_router(admin_order,         prefix="/admin/orders",        tags=["Admin Orders"])
api_router.include_router(admin_rider,         prefix="/admin/riders",        tags=["Admin Riders"])
api_router.include_router(admin_shop,          prefix="/admin/shops",         tags=["Admin Shops"])
api_router.include_router(admin_stats,         prefix="/admin/stats",         tags=["Admin Stats"])
api_router.include_router(admin_subscription,  prefix="/admin/subscriptions", tags=["Admin Subscriptions"])
api_router.include_router(settings_router,     prefix="/admin",               tags=["Admin Settings"])

# ── Parcels ───────────────────────────────────────────────────────────────────
api_router.include_router(parcel,       prefix="/parcels",       tags=["Parcels"])
api_router.include_router(admin_parcel, prefix="/admin/parcels", tags=["Admin Parcels"])
