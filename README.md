# Alkatronic for Home Assistant

Local(-ish) Home Assistant integration for the [Alkatronic](https://focustronic.com/) aquarium
KH/pH dosing controller. Talks to Focustronic's cloud API — this is not an official integration
and isn't affiliated with Focustronic.

## Installation (via HACS)

1. HACS → Integrations → ⋮ (top right) → **Custom repositories**
2. Add this repo's URL, category **Integration**
3. Install **Alkatronic**, restart Home Assistant
4. Settings → Devices & Services → **+ Add Integration** → search **Alkatronic**
5. Enter your Alkatronic account email, password, and device ID (the numeric ID from your
   device's data URL)

## What you get

One device with sensors for KH, pH, acid used, solution added, and the timestamp of the last
recorded reading, all pulled from the same account/device you use in Focustronic's own app.

## Adding more data later

`api.py` holds the API calls, `sensor.py` holds one `AlkatronicSensorDescription` per exposed
value — add a new API call and a couple of new descriptions to extend it.
