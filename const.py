from __future__ import annotations

from ._shared.shared_const import (
    ALARM_STATE_CODES,
    ARM_CONFIRM_CODES,
    ARMED_CODES,
    ATTR_PKU,
    CONF_ARM_ID,
    CONF_BASE_URL,
    CONF_HUMIDITY_LOOPS,
    CONF_HUMIDITY_OFFSET,
    CONF_HUMIDITY_SCALE,
    CONF_PASSWORD,
    CONF_RELAY_PROGRAM,
    CONF_RELAY_TIME,
    CONF_SCAN_INTERVAL,
    CONF_SELECTED_LOOPS,
    CONF_SELECTED_RELAYS,
    CONF_TEMPERATURE_ALARM_HIGH,
    CONF_TEMPERATURE_ALARM_LOW,
    CONF_TEMPERATURE_LOOPS,
    CONF_TEMPERATURE_OFFSET,
    CONF_TEMPERATURE_SCALE,
    CONF_WS_PATH,
    CONFIRM,
    DEFAULT_ARM_ID,
    DEFAULT_RELAY_PROGRAM,
    DEFAULT_RELAY_TIME,
    DEFAULT_BASE_URL,
    DEFAULT_HUMIDITY_OFFSET,
    DEFAULT_HUMIDITY_SCALE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TEMPERATURE_ALARM_HIGH,
    DEFAULT_TEMPERATURE_ALARM_LOW,
    DEFAULT_TEMPERATURE_OFFSET,
    DEFAULT_TEMPERATURE_SCALE,
    DEFAULT_WS_PATH,
    DISARM_CONFIRM_CODES,
    DISARMED_CODES,
    RELAY_PROGRAMS,
    RELAY_PROGRAMS as RELAY_PROGRAM_CODES,
    RELAY_STATE_BLINK,
    RELAY_STATE_NAMES,
    RELAY_STATE_OFF,
    RELAY_STATE_ON,
    RELAY_STATE_UNKNOWN,
    RELAY_TIME_PROGRAMS,
    STATE_NAMES,
    TEMPERATURE_ALARM_CODE,
)

DOMAIN = "techlan_sensor"
PLATFORMS = ["sensor", "binary_sensor", "number", "select", "switch", "button"]

# Версия схемы config entry: minor обновляется при миграциях (async_migrate_entry).
CONFIG_MINOR_VERSION = 4

# Версия интеграции (синхронизировать с manifest.json).
INTEGRATION_VERSION = "0.6.3"

# Идентификатор и параметры родительского устройства.
# Отличается от techlan_ops ("arm_ops"), чтобы устройства двух интеграций
# не смешивались.
PARENT_IDENTIFIER = "arm_sensor"
DEVICE_NAME = "SecurARM Sensor"
DEVICE_MODEL = "ServerSkif WebSocket proxy"
