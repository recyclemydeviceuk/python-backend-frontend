import csv
import io
import zipfile
from datetime import datetime
from typing import List
from app.models.order import Order
from app.utils.logger import logger


async def export_orders_csv(orders: List[Order]) -> bytes:
    """Serialize orders to CSV bytes."""
    output = io.StringIO()
    fieldnames = [
        "Order Number", "Source", "Status", "Customer Name", "Customer Phone",
        "Customer Email", "Device Name", "Network", "Storage", "Device Grade",
        "Offered Price", "Final Price", "Payment Status", "Postage Method",
        "Tracking Number", "Created At",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for order in orders:
        writer.writerow({
            "Order Number": order.order_number,
            "Source": order.source or "",
            "Status": order.status,
            "Customer Name": order.customer_name,
            "Customer Phone": order.customer_phone,
            "Customer Email": order.customer_email or "",
            "Device Name": order.device_name,
            "Network": order.network,
            "Storage": order.storage,
            "Device Grade": order.device_grade,
            "Offered Price": order.offered_price,
            "Final Price": order.final_price or "",
            "Payment Status": order.payment_status,
            "Postage Method": order.postage_method,
            "Tracking Number": order.tracking_number or "",
            "Created At": order.created_at.isoformat(),
        })

    logger.info(f"Exported {len(orders)} orders to CSV")
    return output.getvalue().encode("utf-8")


async def export_devices_csv(devices: list) -> bytes:
    """Serialize devices to CSV bytes."""
    output = io.StringIO()
    fieldnames = [
        "Brand", "Name", "Full Name", "Category", "Is Active",
        "Image URL", "Created At",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for device in devices:
        writer.writerow({
            "Brand": device.brand,
            "Name": device.name,
            "Full Name": device.full_name,
            "Category": device.category,
            "Is Active": device.is_active,
            "Image URL": device.image_url or "",
            "Created At": device.created_at.isoformat(),
        })

    logger.info(f"Exported {len(devices)} devices to CSV")
    return output.getvalue().encode("utf-8")


async def export_pricing_csv(pricing: list) -> bytes:
    """Serialize pricing entries to CSV bytes."""
    output = io.StringIO()
    fieldnames = [
        "Device Name", "Network", "Storage",
        "NEW Price", "GOOD Price", "BROKEN Price", "Updated At",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for p in pricing:
        writer.writerow({
            "Device Name": p.device_name,
            "Network": p.network,
            "Storage": p.storage,
            "NEW Price": p.grade_new,
            "GOOD Price": p.grade_good,
            "BROKEN Price": p.grade_broken,
            "Updated At": p.updated_at.isoformat(),
        })

    logger.info(f"Exported {len(pricing)} pricing entries to CSV")
    return output.getvalue().encode("utf-8")


async def export_analytics_csv(analytics_data: dict) -> bytes:
    """Serialize analytics summary to CSV bytes."""
    lines = []
    summary = analytics_data.get("summary", {})
    lines.append("SUMMARY")
    lines.append(f"Total Orders,{summary.get('totalOrders', 0)}")
    lines.append(f"Total Revenue,£{summary.get('totalRevenue', 0)}")
    lines.append(f"Paid Orders,{summary.get('paidOrders', 0)}")
    lines.append(f"Average Order Value,£{summary.get('avgOrderValue', 0)}")
    lines.append("")

    lines.append("STATUS BREAKDOWN")
    lines.append("Status,Count")
    for item in analytics_data.get("statusBreakdown", []):
        lines.append(f"{item.get('_id', '')},{item.get('count', 0)}")
    lines.append("")

    lines.append("TOP DEVICES")
    lines.append("Device,Order Count,Total Value")
    for item in analytics_data.get("topDevices", []):
        lines.append(f"{item.get('_id', '')},{item.get('count', 0)},£{item.get('totalValue', 0)}")

    logger.info("Exported analytics to CSV")
    return "\n".join(lines).encode("utf-8")


async def export_all_zip(orders_csv: bytes, devices_csv: bytes, pricing_csv: bytes) -> bytes:
    """Bundle orders, devices and pricing CSVs into a ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("orders.csv", orders_csv)
        zf.writestr("devices.csv", devices_csv)
        zf.writestr("pricing.csv", pricing_csv)
    logger.info("Created ZIP archive with all data")
    return buf.getvalue()
