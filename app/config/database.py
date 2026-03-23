from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.config.settings import settings
from app.utils.logger import logger


async def connect_db():
    """Initialize MongoDB connection and Beanie ODM."""
    from app.models.admin import Admin
    from app.models.api_log import ApiLog
    from app.models.brand import Brand
    from app.models.category import Category
    from app.models.contact_submission import ContactSubmission
    from app.models.counter_offer import CounterOffer
    from app.models.device import Device
    from app.models.device_condition import DeviceCondition
    from app.models.feed_log import FeedLog
    from app.models.ip_whitelist import IpWhitelist
    from app.models.network import Network
    from app.models.order import Order
    from app.models.order_status import OrderStatus
    from app.models.otp import OTP
    from app.models.partner import Partner
    from app.models.payment_status import PaymentStatus
    from app.models.pricing import Pricing
    from app.models.storage_option import StorageOption

    try:
        client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=5000,
            maxPoolSize=10,
        )
        db = client[settings.DB_NAME]

        await init_beanie(
            database=db,
            allow_index_dropping=True,
            document_models=[
                Admin,
                ApiLog,
                Brand,
                Category,
                ContactSubmission,
                CounterOffer,
                Device,
                DeviceCondition,
                FeedLog,
                IpWhitelist,
                Network,
                Order,
                OrderStatus,
                OTP,
                Partner,
                PaymentStatus,
                Pricing,
                StorageOption,
            ],
        )

        logger.info(f"MongoDB connected: {settings.DB_NAME} @ {settings.MONGODB_URI}")
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        raise


async def close_db():
    """Close MongoDB connection."""
    from motor.motor_asyncio import AsyncIOMotorClient
    logger.info("MongoDB connection closed")
