"""
Seed script: reads data/tours.json and inserts tours into the itineraries table.

Usage:
    uv run scripts/seed_tours.py [--dry-run]

Without --dry-run the script requires DATABASE_URL in environment (or .env).
With    --dry-run it just validates and logs the loaded tours.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOURS_FILE = ROOT / "data" / "tours.json"

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Seed tours into itineraries table.")
parser.add_argument(
    "--dry-run",
    action="store_true",
    default=False,
    help="Validate and log tours without touching the database.",
)
args = parser.parse_args()


# ── Load & validate ───────────────────────────────────────────────────────────

if not TOURS_FILE.exists():
    sys.exit(f"[ERROR] File not found: {TOURS_FILE}")

with TOURS_FILE.open(encoding="utf-8") as f:
    tours: list[dict] = json.load(f)

required_fields = {
    "id", "destination", "hotel_name", "hotel_stars",
    "price_usd", "duration_nights", "departure_date", "meal_plan", "description",
}

errors: list[str] = []
for i, tour in enumerate(tours):
    missing = required_fields - tour.keys()
    if missing:
        errors.append(f"tour[{i}] missing fields: {missing}")

if errors:
    for e in errors:
        print(f"[WARN] {e}")

print(f"[INFO] Loaded {len(tours)} tours from {TOURS_FILE.relative_to(ROOT)}")

# ── Stats ─────────────────────────────────────────────────────────────────────

destinations = Counter(t["destination"] for t in tours)
stars = Counter(t["hotel_stars"] for t in tours)
meal_plans = Counter(t["meal_plan"] for t in tours)
prices = [t["price_usd"] for t in tours]

print(f"[INFO] Destinations ({len(destinations)}): {dict(destinations.most_common())}")
print(f"[INFO] Stars distribution: {dict(sorted(stars.items()))}")
print(f"[INFO] Meal plans: {dict(meal_plans)}")
print(f"[INFO] Price range: {min(prices)} – {max(prices)} USD "
      f"(avg: {sum(prices)//len(prices)} USD)")

if args.dry_run:
    print("[DRY-RUN] Skipping database insertion. All tours validated OK.")
    sys.exit(0)


# ── DB insertion ──────────────────────────────────────────────────────────────
# Requires: DATABASE_URL env var (e.g. postgresql+asyncpg://user:pass@host/db)

try:
    import asyncio
    import asyncpg
except ImportError:
    sys.exit("[ERROR] asyncpg is not installed. Run: uv add asyncpg")

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    # Try loading from .env
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                DATABASE_URL = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

if not DATABASE_URL:
    sys.exit("[ERROR] DATABASE_URL is not set. Use --dry-run or set DATABASE_URL.")

# Strip asyncpg scheme prefix if needed (asyncpg uses plain DSN)
dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

INSERT_SQL = """
    INSERT INTO itineraries (
        id, destination, hotel_name, hotel_stars,
        price_usd, duration_nights, departure_date, meal_plan, description
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7::date, $8, $9
    )
    ON CONFLICT (id) DO NOTHING
"""


async def seed(tours: list[dict]) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        inserted = 0
        skipped = 0
        async with conn.transaction():
            for t in tours:
                result = await conn.execute(
                    INSERT_SQL,
                    t["id"],
                    t["destination"],
                    t["hotel_name"],
                    t["hotel_stars"],
                    t["price_usd"],
                    t["duration_nights"],
                    t["departure_date"],
                    t["meal_plan"],
                    t["description"],
                )
                # asyncpg returns "INSERT 0 N"
                n = int(result.split()[-1])
                inserted += n
                skipped += 1 - n
        print(f"[OK] Inserted {inserted} rows, skipped {skipped} (already exist).")
    finally:
        await conn.close()


asyncio.run(seed(tours))
