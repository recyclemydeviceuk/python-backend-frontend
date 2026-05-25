"""
Standalone CLI script: enforce NEW >= GOOD >= BROKEN on every Pricing row.

Reuses the exact same logic the FastAPI startup migration runs
(`_migrate_pricing_hierarchy` in main.py) so behaviour is identical
whether the migration fires automatically on boot or you run this script
manually against a backup / staging / production database.

Usage:
    # Use the MONGODB_URI from .env (default)
    python scripts/fix_pricing_hierarchy.py

    # Or override the URI / db name for a one-off run
    MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/cmm_prod" \\
        python scripts/fix_pricing_hierarchy.py

    # Dry-run mode — prints what would change without writing
    python scripts/fix_pricing_hierarchy.py --dry-run

Output (example):
    Connected to MongoDB: cmm_prod
    Scanning 412 pricing rows...
      [FIX]  Apple iPhone 15 Pro Max / 256GB / EE        (240, 455, 852) -> (852, 455, 240)
      [FIX]  Samsung Galaxy S24 Ultra / 512GB / Unlocked  (0, 0, 700)    -> (805, 700, 280)
      [OK]   Apple iPhone 14 Pro / 128GB / O2             already canonical
    -------------------------------------------------------------
    examined=412  fixed=137  skipped_empty=8  already_canonical=267
    Done.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `app.*` imports resolve when
# running as `python scripts/fix_pricing_hierarchy.py` from the repo root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from motor.motor_asyncio import AsyncIOMotorClient

from app.config.settings import settings
from main import _compute_hierarchy


async def run(dry_run: bool = False) -> int:
    client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=10000)
    db = client[settings.DB_NAME]
    coll = db["pricings"]

    total = await coll.count_documents({})
    print(f"Connected to MongoDB: {settings.DB_NAME}")
    print(f"Scanning {total} pricing rows..." + ("  (dry-run, nothing will be written)" if dry_run else ""))

    examined = fixed = skipped_empty = already_ok = 0
    cursor = coll.find({})
    async for doc in cursor:
        examined += 1
        new    = float(doc.get("gradeNew")    or doc.get("grade_new")    or 0)
        good   = float(doc.get("gradeGood")   or doc.get("grade_good")   or 0)
        broken = float(doc.get("gradeBroken") or doc.get("grade_broken") or 0)

        canonical = _compute_hierarchy(new, good, broken)
        label = f"{doc.get('deviceName') or doc.get('device_name') or doc.get('_id')} / {doc.get('storage', '?')} / {doc.get('network', '?')}"

        if canonical is None:
            skipped_empty += 1
            continue

        already_canonical = (
            float(doc.get("gradeNew",    0) or 0) == canonical["gradeNew"]    and
            float(doc.get("gradeGood",   0) or 0) == canonical["gradeGood"]   and
            float(doc.get("gradeBroken", 0) or 0) == canonical["gradeBroken"] and
            float(doc.get("grade_new",    0) or 0) == canonical["gradeNew"]    and
            float(doc.get("grade_good",   0) or 0) == canonical["gradeGood"]   and
            float(doc.get("grade_broken", 0) or 0) == canonical["gradeBroken"]
        )
        if already_canonical:
            already_ok += 1
            print(f"  [OK]   {label:<70}  already canonical")
            continue

        print(
            f"  [FIX]  {label:<70}  "
            f"({new:g}, {good:g}, {broken:g}) -> "
            f"({canonical['gradeNew']:g}, {canonical['gradeGood']:g}, {canonical['gradeBroken']:g})"
        )

        if not dry_run:
            await coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "gradeNew":     canonical["gradeNew"],
                    "gradeGood":    canonical["gradeGood"],
                    "gradeBroken":  canonical["gradeBroken"],
                    "grade_new":    canonical["gradeNew"],
                    "grade_good":   canonical["gradeGood"],
                    "grade_broken": canonical["gradeBroken"],
                }},
            )
            fixed += 1

    print("-" * 61)
    print(f"examined={examined}  "
          f"fixed={fixed}  "
          f"skipped_empty={skipped_empty}  "
          f"already_canonical={already_ok}")
    print("Done." if not dry_run else "Done (dry-run — no writes performed).")
    client.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce NEW>=GOOD>=BROKEN on every Pricing row")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would change without writing to MongoDB.",
    )
    args = parser.parse_args()
    return asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
