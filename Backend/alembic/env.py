import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..', '..')))


from app.models.base import Base
from app.models.user import User
from app.models.token import Token
from app.models.active_session import ActiveSession
from app.models.ad import Ad
from app.models.admin import AdminUser
from app.models.audit_log import AuditLog
from app.models.cart import Cart
from app.models.commission import CommissionConfig
from app.models.complaint import Complaint
from app.models.customer_profile import CustomerProfile
from app.models.discount import DiscountRule
from app.models.ledger_entry import LedgerEntry
from app.models.mandla import Mandla
from app.models.mini_website import MiniWebsite
from app.models.notification import Notification
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.otp import OTP
from app.models.parcel import Parcel
from app.models.parcel_rate import ParcelRate
from app.models.payment import Payment
from app.models.pincode import Pincode
from app.models.product import Product
from app.models.product_stock_ledger import ProductStockLedger
from app.models.rating import Rating
from app.models.rider import Rider
from app.models.rider_profile import RiderProfile
from app.models.role_application import RoleApplication
from app.models.shop import Shop
from app.models.shop_category import ShopCategory
from app.models.shop_profile import ShopProfile
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.udhar_account import UdharAccount
from app.models.udhar_transaction import UdharTransaction
from app.models.wallet import Wallet
from app.models.withdrawal_request import WithdrawalRequest

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
