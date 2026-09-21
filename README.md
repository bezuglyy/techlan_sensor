# Techlan Sensor
![Release](https://img.shields.io/github/v/release/bezuglyy/techlan_sensor?label=Release&style=flat-square) ![HACS](https://img.shields.io/badge/HACS-Custom%20Repository-purple?style=flat-square) ![License](https://img.shields.io/github/license/bezuglyy/techlan_sensor?style=flat-square) ![HA](https://img.shields.io/badge/HA-2025.1%2B-2ea44f?style=flat-square)
Кастомная интеграция для [Home Assistant](https://www.home-assistant.io) · версия **0.5.0**.
![icon](brand/icon.png)
| | |
|---|---|
| Домен | `techlan_sensor` |
| Версия | 0.5.0 |
| Тип | custom integration |
## Описание
Сенсоры шлейфов охранной системы ServerSkif (Techlan).
### Возможности
- Полная настройка через UI (config flow)
### Изменения 0.5.0
- **Только чтение климата** — интеграция больше не содержит управляющих сервисов/кнопок (управление ОПС — в `techlan_ops`).
- **`number`-сущности:** `temperature_scale`/`offset`, `humidity_scale`/`offset`, `temperature_alarm_low`/`high`.
- Климат считается как `(temperature|adc) × scale + offset`; тревога по температуре — по коду 206 и порогам.
- **Постоянное read-only WebSocket-соединение** с реконнектом.
- **Диагностика**, **Repairs**, enum-классы, миграция схемы; **фирменный брендинг** (светлая/тёмная тема).
### Установка
1. Скопируйте папку `custom_components/techlan_sensor/` в каталог `custom_components/` конфигурации Home Assistant.
2. Перезапустите Home Assistant.
3. Настройки → Устройства и службы → Добавить интеграцию → **Techlan Sensor**.
> Установка через HACS: добавьте репозиторий `https://github.com/bezuglyy/techlan_sensor` как Custom repository (категория Integration).
---
## Description
ServerSkif (Techlan) security loop sensors.
### Features
- Full configuration via UI (config flow)
### Installation
1. Copy the `custom_components/techlan_sensor/` folder into the `custom_components/` directory of your Home Assistant configuration.
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **Techlan Sensor**.
> HACS: add `https://github.com/bezuglyy/techlan_sensor` as a Custom repository (category Integration).
---
**Автор / Author:**
![Bezuglyj E.N.](logo-bezuglyj.png)
## License / Лицензия
MIT
