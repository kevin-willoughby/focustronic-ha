"""Constants for the Alkatronic integration."""

DOMAIN = "alkatronic"

CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DOSETRONIC_ID = "dosetronic_id"

BASE_URL = "https://alkatronic.focustronic.com"
LOGIN_ENDPOINT = f"{BASE_URL}/users/login"
DEVICES_ENDPOINT = f"{BASE_URL}/api/v2/users/self/devices"
RECORDS_ENDPOINT = f"{BASE_URL}/api/v2/devices/alkatronic/{{device_id}}/data/test-records"
SCHEDULE_TEST_ENDPOINT = f"{BASE_URL}/users/devices/{{device_id}}/scheduletest"

DEVICE_STATUS_UPDATE_INTERVAL_MINUTES = 15

DEFAULT_HISTORY_DAYS = 7
DEFAULT_UPDATE_INTERVAL_MINUTES = 15

# Some fields the API returns are scaled x100 (e.g. 809 == 8.09 dKH).
SCALED_FIELDS = {"kh_value", "ph_value"}
