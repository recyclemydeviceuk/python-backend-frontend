import csv
import io
from datetime import datetime
from typing import Optional
from app.models.device import Device
from app.models.pricing import Pricing
from app.utils.logger import logger


async def generate_pricing_feed_csv(
    brand: Optional[str] = None,
    active_only: bool = True,
    category: Optional[str] = None,
) -> tuple[bytes, int]:
    device_col = Device.get_motor_collection()
    pricing_col = Pricing.get_motor_collection()

    # Build device filter
    conditions: list = []
    if active_only:
        conditions.append({"$or": [{"isActive": True}, {"is_active": True}]})
    if brand:
        conditions.append({"brand": {"$regex": f"^{brand}$", "$options": "i"}})
    if category:
        conditions.append({"category": {"$regex": f"^{category}$", "$options": "i"}})
    device_match: dict = {"$and": conditions} if conditions else {}

    devices_raw = await device_col.find(device_match).to_list(length=None)
    logger.info(f"Feed: found {len(devices_raw)} devices")

    # Fetch ALL pricing docs once
    pricing_raw = await pricing_col.find({}).to_list(length=None)
    logger.info(f"Feed: found {len(pricing_raw)} pricing rows")

    # Build pricing map keyed by device_id string (handle both ObjectId and string stored values)
    pricing_map: dict[str, list] = {}
    for p in pricing_raw:
        # Pricing may store deviceId as ObjectId or as a string
        raw_did = p.get("deviceId") or p.get("device_id")
        if raw_did is None:
            continue
        did_str = str(raw_did)
        pricing_map.setdefault(did_str, []).append(p)

    output = io.StringIO()
    fieldnames = [
        "Device ID",
        "Brand",
        "Device Name",
        "Full Name",
        "Category",
        "Storage",
        "Network",
        "NEW",
        "GOOD",
        "BROKEN",
        "Image URL",
        "Active",
        "Last Updated",
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    row_count = 0

    for device in devices_raw:
        device_id = str(device["_id"])
        pricing_entries = pricing_map.get(device_id, [])

        brand_val = (device.get("brand") or "").title()
        name_val = device.get("name") or ""
        full_name_val = device.get("fullName") or device.get("full_name") or name_val
        category_val = device.get("category") or ""
        image_url_val = device.get("imageUrl") or device.get("image_url") or ""
        is_active_val = device.get("isActive", device.get("is_active", True))
        updated_at_raw = device.get("updatedAt") or device.get("updated_at")
        device_updated = updated_at_raw.isoformat() if updated_at_raw else datetime.utcnow().isoformat()

        if pricing_entries:
            for p in pricing_entries:
                updated_raw = p.get("updatedAt") or p.get("updated_at")
                last_updated = updated_raw.isoformat() if updated_raw else device_updated

                grade_new = float(p.get("gradeNew") or p.get("grade_new") or 0)
                grade_good = float(p.get("gradeGood") or p.get("grade_good") or 0)
                grade_broken = float(p.get("gradeBroken") or p.get("grade_broken") or 0)
                
                storage_val = p.get("storage") or ""
                full_name_with_storage = f"{full_name_val} {storage_val}".strip() if storage_val else full_name_val

                writer.writerow({
                    "Device ID": device_id,
                    "Brand": brand_val,
                    "Device Name": name_val,
                    "Full Name": full_name_with_storage,
                    "Category": category_val,
                    "Storage": storage_val,
                    "Network": p.get("network") or "",
                    "NEW": f"{grade_new:.2f}",
                    "GOOD": f"{grade_good:.2f}",
                    "BROKEN": f"{grade_broken:.2f}",
                    "Image URL": image_url_val,
                    "Active": "true" if is_active_val else "false",
                    "Last Updated": last_updated,
                })
                row_count += 1
        else:
            # Device exists but no pricing yet — still include it
            writer.writerow({
                "Device ID": device_id,
                "Brand": brand_val,
                "Device Name": name_val,
                "Full Name": full_name_val,
                "Category": category_val,
                "Storage": "",
                "Network": "",
                "NEW": "0.00",
                "GOOD": "0.00",
                "BROKEN": "0.00",
                "Image URL": image_url_val,
                "Active": "true" if is_active_val else "false",
                "Last Updated": device_updated,
            })
            row_count += 1

    logger.info(f"Feed CSV generated: {row_count} rows")
    return output.getvalue().encode("utf-8"), row_count
