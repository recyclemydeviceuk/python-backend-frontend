import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

async def seed():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
    db = client.cashmymobile
    
    # Sample devices
    devices = [
        {
            "brand": "Apple",
            "name": "iPhone 15 Pro Max",
            "full_name": "Apple iPhone 15 Pro Max",
            "category": "Smartphone",
            "image_url": "https://zennara-storage.s3.ap-south-1.amazonaws.com/device-images/1771189550215-default%20(1).png",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "brand": "Apple",
            "name": "iPhone 15 Pro",
            "full_name": "Apple iPhone 15 Pro",
            "category": "Smartphone",
            "image_url": "https://zennara-storage.s3.ap-south-1.amazonaws.com/device-images/1771189550215-default%20(1).png",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "brand": "Apple",
            "name": "iPhone 14",
            "full_name": "Apple iPhone 14",
            "category": "Smartphone",
            "image_url": "https://zennara-storage.s3.ap-south-1.amazonaws.com/device-images/1771189550215-default%20(1).png",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "brand": "Samsung",
            "name": "Galaxy S24 Ultra",
            "full_name": "Samsung Galaxy S24 Ultra",
            "category": "Smartphone",
            "image_url": "https://zennara-storage.s3.ap-south-1.amazonaws.com/device-images/1771189550215-default%20(1).png",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "brand": "Samsung",
            "name": "Galaxy S23",
            "full_name": "Samsung Galaxy S23",
            "category": "Smartphone",
            "image_url": "https://zennara-storage.s3.ap-south-1.amazonaws.com/device-images/1771189550215-default%20(1).png",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    ]
    
    await db.devices.delete_many({})
    result = await db.devices.insert_many(devices)
    print(f"✅ Inserted {len(result.inserted_ids)} devices")
    
    # Add some basic pricing
    pricings = []
    for dev_id in result.inserted_ids:
        for storage in ["128GB", "256GB", "512GB"]:
            pricings.append({
                "device_id": str(dev_id),
                "device_name": "Device",
                "network": "Unlocked",
                "storage": storage,
                "grade_new": 400.0,
                "grade_good": 300.0,
                "grade_broken": 150.0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
    
    await db.pricings.delete_many({})
    result2 = await db.pricings.insert_many(pricings)
    print(f"✅ Inserted {len(result2.inserted_ids)} pricing entries")
    
    client.close()

asyncio.run(seed())
