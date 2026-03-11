from typing import List, Optional
from app.models.pricing import Pricing
from app.utils.logger import logger


async def upsert_pricing(
    device_id: str,
    device_name: str,
    network: str,
    storage: str,
    grade_new: float,
    grade_good: float,
    grade_broken: float,
) -> Pricing:
    """Create or update a pricing record."""
    existing = await Pricing.find_one(
        Pricing.device_id == device_id,
        Pricing.network == network,
        Pricing.storage == storage,
    )
    if existing:
        existing.grade_new = grade_new
        existing.grade_good = grade_good
        existing.grade_broken = grade_broken
        existing.device_name = device_name
        await existing.save()
        return existing

    pricing = Pricing(
        device_id=device_id,
        device_name=device_name,
        network=network,
        storage=storage,
        grade_new=grade_new,
        grade_good=grade_good,
        grade_broken=grade_broken,
    )
    await pricing.insert()
    return pricing


async def get_max_price_per_device(device_ids: List[str]) -> dict:
    """Return {device_id: max_price} for a list of device IDs."""
    result = {}
    for did in device_ids:
        records = await Pricing.find(Pricing.device_id == did).to_list()
        if records:
            max_p = max(
                max(r.grade_new, r.grade_good, r.grade_broken) for r in records
            )
            result[did] = max_p
    return result
