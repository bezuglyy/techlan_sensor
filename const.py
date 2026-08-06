from __future__ import annotations

DOMAIN = "techlan_sensor"
PLATFORMS = ["sensor", "binary_sensor"]

CONF_BASE_URL = "base_url"
CONF_ARM_ID = "arm_id"
CONF_PASSWORD = "password"
CONF_WS_PATH = "ws_path"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SELECTED_LOOPS = "selected_loops"
CONF_TEMPERATURE_LOOPS = "temperature_loops"
CONF_TEMPERATURE_SCALE = "temperature_scale"
CONF_TEMPERATURE_OFFSET = "temperature_offset"
CONF_HUMIDITY_LOOPS = "humidity_loops"
CONF_HUMIDITY_SCALE = "humidity_scale"
CONF_HUMIDITY_OFFSET = "humidity_offset"
CONFIRM = "confirm"

DEFAULT_BASE_URL = "http://192.168.100.111:18081"
DEFAULT_ARM_ID = "techlan"
DEFAULT_WS_PATH = "/skif-ws"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_TEMPERATURE_SCALE = 1.0
DEFAULT_TEMPERATURE_OFFSET = 0.0
DEFAULT_HUMIDITY_SCALE = 1.0
DEFAULT_HUMIDITY_OFFSET = 0.0

ATTR_PKU = "pku"

# ServerSkif event/state codes that should be surfaced as active alarms.
# The ARM web client treats these as alarm or operationally important states.
ALARM_STATE_CODES = {
    3, 18, 27, 33, 37, 40, 44, 45, 58, 79, 118, 137, 138, 139,
    141, 143, 144, 145, 146, 147, 149, 150, 151, 157, 159, 160,
    161, 162, 214, 216, 220, 221, 250, 252,
}

STATE_NAMES = {
    1: "Норма сети 220 В",
    7: "Исполнительное устройство включено вручную",
    8: "Исполнительное устройство выключено вручную",
    9: "Устройство дистанционного пуска активировано",
    10: "Устройство дистанционного пуска в норме",
    23: "Идёт взятие",
    24: "Взят",
    35: "Технологический ШС в норме",
    36: "Технологический ШС нарушен",
    47: "ДПЛС в норме",
    80: "Датчик затопления в норме",
    83: "Термометр в норме",
    91: "Канал связи в норме",
    109: "Снят",
    117: "Снят и в норме",
    119: "Снят и нарушен",
    123: "Выход (реле) в норме",
    127: "Связь с реле восстановлена",
    136: "Напряжение питания в норме",
    152: "Корпус закрыт",
    158: "Внутренняя зона в норме",
    188: "Связь с ШС в норме",
    191: "ДПЛС1 в норме",
    195: "Токопотребление в норме",
    197: "Зарядное устройство в норме",
    199: "Источник питания в норме",
    201: "ДПЛС2 в норме",
    206: "Температура ниже заданного значения",
    218: "RS-485 в норме",
}
