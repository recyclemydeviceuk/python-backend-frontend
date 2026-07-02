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
        "Customer Email", "Address", "City", "Postcode",
        "Device Name", "Network", "Storage", "Device Grade",
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
            # Royal Mail labels need the postal address — these columns were
            # missing entirely before, so the address mapped to nothing.
            "Address": order.customer_address or "",
            "City": getattr(order, "city", None) or "",
            "Postcode": getattr(order, "postcode", None) or "",
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


def orders_csv_from_rows(rows: list) -> bytes:
    """Serialize already-serialized order dicts (from the orders router's
    _serialize_raw) to CSV. Includes every customer-facing field — contact,
    address, device, prices, counter offer, and the bank details the payments
    team needs to make the transfer."""
    output = io.StringIO()
    fieldnames = [
        "Order Number", "Source", "Partner", "Status", "Customer Name",
        "Customer Phone", "Customer Email", "Address", "City", "Postcode",
        "Device Name", "Network", "Storage", "Device Grade",
        "Offered Price", "Final Price", "Revised Price (Counter Offer)",
        "Counter Offer Status", "Payment Method", "Payment Status",
        "Account Name", "Account Number", "Sort Code",
        "Postage Method", "Tracking Number", "Transaction ID",
        "Created At", "Updated At",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for row in rows:
        payout = row.get("payoutDetails") or {}
        counter = row.get("counterOffer") or {}
        writer.writerow({
            "Order Number": row.get("orderNumber") or "",
            "Source": row.get("source") or "",
            "Partner": row.get("partnerName") or "",
            "Status": row.get("status") or "",
            "Customer Name": row.get("customerName") or "",
            "Customer Phone": row.get("customerPhone") or "",
            "Customer Email": row.get("customerEmail") or "",
            "Address": row.get("customerAddress") or "",
            "City": row.get("city") or "",
            "Postcode": row.get("postcode") or "",
            "Device Name": row.get("deviceName") or "",
            "Network": row.get("network") or "",
            "Storage": row.get("storage") or "",
            "Device Grade": row.get("deviceGrade") or "",
            "Offered Price": row.get("offeredPrice", ""),
            "Final Price": row.get("finalPrice") if row.get("finalPrice") is not None else "",
            "Revised Price (Counter Offer)": counter.get("revisedPrice") if counter.get("revisedPrice") is not None else "",
            "Counter Offer Status": counter.get("status") or "",
            "Payment Method": row.get("paymentMethod") or "",
            "Payment Status": row.get("paymentStatus") or "",
            "Account Name": payout.get("accountName") or "",
            "Account Number": payout.get("accountNumber") or "",
            "Sort Code": payout.get("sortCode") or "",
            "Postage Method": row.get("postageMethod") or "",
            "Tracking Number": row.get("trackingNumber") or "",
            "Transaction ID": row.get("transactionId") or "",
            "Created At": row.get("createdAt") or "",
            "Updated At": row.get("updatedAt") or "",
        })

    logger.info(f"Exported {len(rows)} orders to CSV (filtered export)")
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
