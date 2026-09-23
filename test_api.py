"""Standalone smoke test — no Home Assistant needed.

Run from the folder containing custom_components/:
    python3 test_api.py

How this avoids needing Home Assistant installed:
custom_components/alkatronic/__init__.py imports real Home Assistant
modules, and a normal `from custom_components.alkatronic.api import ...`
would run that __init__.py first. To dodge that, we register a fake, empty
"alkatronic" package in sys.modules *before* importing anything from it —
Python's import system then finds api.py and const.py as normal submodules
(so their `from .const import ...` relative imports still work), but never
actually executes the real __init__.py.
"""
import asyncio
import getpass
import importlib
import sys
import types
from pathlib import Path

import aiohttp

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# --- register fake empty packages so relative imports resolve normally ---
fake_custom_components = types.ModuleType("custom_components")
fake_custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules["custom_components"] = fake_custom_components

fake_alkatronic = types.ModuleType("custom_components.alkatronic")
fake_alkatronic.__path__ = [str(ROOT / "custom_components" / "alkatronic")]
sys.modules["custom_components.alkatronic"] = fake_alkatronic

# now a completely normal import — finds api.py as a submodule, and api.py's
# own `from .const import ...` resolves against the fake package above.
api = importlib.import_module("custom_components.alkatronic.api")
AlkatronicClient = api.AlkatronicClient


async def main() -> None:
    email = input("Alkatronic email: ")
    password = getpass.getpass("Alkatronic password: ")

    async with aiohttp.ClientSession() as session:
        client = AlkatronicClient(session, email, password, "")

        print("\nLogging in...")
        await client.async_login()
        print("Login OK.")
        print (client._token);

        print("\nFetching devices...")
        devices_by_type = await client.async_get_devices()
        for device_type, devices in devices_by_type.items():
            print(f"  {device_type}: {len(devices)} device(s)")
            for d in devices:
                name = d.get("friendly_name") or d.get("serial_number")
                print(f"    - id={d['id']}  name={name}")

        alkatronic_devices = devices_by_type.get("alkatronic", [])
        if not alkatronic_devices:
            print("\nNo Alkatronic device found — stopping here.")
            return

        device_id = str(alkatronic_devices[0]["id"])
        print(f"\nFetching records for device {device_id}...")
        client._device_id = device_id  # normally set via constructor
        records = await client.async_get_records()
        print(f"Got {len(records)} records. Newest first, top 3:")
        for r in records[:3]:
            kh = r["kh_value"] / 100
            ph = r["ph_value"] / 100
            print(f"    time={r['record_time']}  KH={kh}  pH={ph}")


if __name__ == "__main__":
    asyncio.run(main())
