import csv
import io
from typing import Tuple
from app.models.device import Device
from app.models.pricing import Pricing
from app.utils.logger import logger


async def import_devices_from_csv(content: bytes) -> Tuple[int, int, list]:
    """
    Parse CSV and upsert devices.
    Returns (imported_count, skipped_count, errors).
    Expected columns: brand, name, full_name, category, image_url
    """
    imported = 0
    skipped = 0
    errors = []

    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        for i, row in enumerate(reader, start=2):
            try:
                brand = row.get("brand", "").strip()
                name = row.get("name", "").strip()
                full_name = row.get("full_name", "").strip()
                category = row.get("category", "").strip()

                if not all([brand, name, full_name, category]):
                    errors.append(f"Row {i}: missing required fields")
                    skipped += 1
                    continue

                existing = await Device.find_one(Device.full_name == full_name)
                if existing:
                    skipped += 1
                    continue

                device = Device(
                    brand=brand,
                    name=name,
                    full_name=full_name,
                    category=category,
                    image_url=row.get("image_url", "").strip() or None,
                )
                await device.insert()
                imported += 1
            except Exception as e:
                errors.append(f"Row {i}: {str(e)}")
                skipped += 1

    except Exception as e:
        logger.error(f"CSV import error: {e}")
        raise

    logger.info(f"CSV import complete: {imported} imported, {skipped} skipped")
    return imported, skipped, errors


async def import_pricing_from_csv(content: bytes) -> Tuple[int, int, list]:
    """
    Parse CSV and upsert pricing.
    Expected columns: device_id, device_name, network, storage, grade_new, grade_good, grade_broken
    """
    imported = 0
    skipped = 0
    errors = []

    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        for i, row in enumerate(reader, start=2):
            try:
                device_id = row.get("device_id", "").strip()
                device_name = row.get("device_name", "").strip()
                network = row.get("network", "").strip()
                storage = row.get("storage", "").strip()

                if not all([device_id, device_name, network, storage]):
                    errors.append(f"Row {i}: missing required fields")
                    skipped += 1
                    continue

                existing = await Pricing.find_one(
                    Pricing.device_id == device_id,
                    Pricing.network == network,
                    Pricing.storage == storage,
                )
                if existing:
                    existing.grade_new = float(row.get("grade_new", 0))
                    existing.grade_good = float(row.get("grade_good", 0))
                    existing.grade_broken = float(row.get("grade_broken", 0))
                    await existing.save()
                else:
                    pricing = Pricing(
                        device_id=device_id,
                        device_name=device_name,
                        network=network,
                        storage=storage,
                        grade_new=float(row.get("grade_new", 0)),
                        grade_good=float(row.get("grade_good", 0)),
                        grade_broken=float(row.get("grade_broken", 0)),
                    )
                    await pricing.insert()
                imported += 1
            except Exception as e:
                errors.append(f"Row {i}: {str(e)}")
                skipped += 1

    except Exception as e:
        logger.error(f"Pricing CSV import error: {e}")
        raise

    return imported, skipped, errors
