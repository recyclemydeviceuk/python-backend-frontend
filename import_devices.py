import asyncio
import json
from pathlib import Path
from app.config.database import connect_db, close_db
from app.models.device import Device
from datetime import datetime


async def import_devices():
    await connect_db()
    
    # Load devices from backend export
    json_path = Path(__file__).parent.parent / "backend" / "exports" / "devices_export_2026-03-02T15-08-53-474Z.json"
    
    if not json_path.exists():
        print(f"❌ File not found: {json_path}")
        return
    
    with open(json_path, 'r', encoding='utf-8') as f:
        devices_data = json.load(f)
    
    print(f"📦 Found {len(devices_data)} devices to import")
    
    # Clear existing devices
    deleted = await Device.find_all().delete()
    print(f"🗑️  Deleted {deleted.deleted_count if deleted else 0} existing devices")
    
    # Import devices
    imported = 0
    for d in devices_data:
        device = Device(
            brand=d.get('brand', 'Unknown'),
            name=d.get('name', ''),
            full_name=d.get('fullName', ''),
            category=d.get('category', 'Smartphone'),
            image_url=d.get('imageUrl'),
            is_active=d.get('isActive', True),
            specifications=d.get('specifications'),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await device.insert()
        imported += 1
        print(f"✅ Imported: {device.full_name}")
    
    print(f"\n🎉 Successfully imported {imported} devices")
    await close_db()


if __name__ == "__main__":
    asyncio.run(import_devices())
