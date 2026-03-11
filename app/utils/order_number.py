import random
import string
from app.utils.logger import logger


def generate_order_number(prefix: str = "CMM") -> str:
    """Generate a unique order number like CMM-XXXXXX."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"{prefix}-{suffix}"


async def generate_unique_order_number() -> str:
    """Generate and verify uniqueness against DB."""
    from app.models.order import Order

    for attempt in range(10):
        number = generate_order_number()
        existing = await Order.find_one(Order.order_number == number)
        if not existing:
            return number
        logger.warning(f"Order number collision on attempt {attempt + 1}: {number}")

    raise RuntimeError("Failed to generate unique order number after 10 attempts")
