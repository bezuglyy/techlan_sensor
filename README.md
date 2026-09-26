# SecurARM Sensor — интеграция Home Assistant (климат, реле, считыватели)

> **Изменения 1.0.0 (26.09.2026):** домен переименован `techlan_sensor` → **`securarm_sensor`** (BREAKING). Добавлено управление **считывателями С2000-2** (`controlReader`) и реле; каждый прибор — отдельное устройство HA. Логика: [docs/c2000-2-relays-readers.md](https://github.com/bezuglyy/securarm/blob/main/docs/c2000-2-relays-readers.md).

# SecurARM Sensor
![Release](https://img.shields.io/github/v/release/bezuglyy/techlan_sensor?label=Release&style=flat-square) ![HACS](https://img.shields.io/badge/HACS-Custom%20Repository-purple?style=flat-square) ![License](https://img.shields.io/github/license/bezuglyy/techlan_sensor?style=flat-square) ![HA](https://img.shields.io/badge/HA-2025.1%2B-2ea44f?style=flat-square)
Кастомная интеграция для [Home Assistant](https://www.home-assistant.io) · версия **0.6.3**.
![icon](brand/icon.png)
| | |
|---|---|
| Домен | `techlan_sensor` |
| Версия | 0.6.3 |
| Тип | custom integration |
## Описание
Сенсоры шлейфов охранной системы ServerSkif (**SecurARM**) и **управление реле**. Отображаемое имя интеграции — **SecurARM Sensor**; домен `techlan_sensor` и `entity_id` не меняются.
### Возможности
- Полная настройка через UI (config flow)
- Климат: АЦП шлейфов, температура/влажность с калибровкой (`scale`/`offset`) и порогами тревоги
- **Реле** (управляемые выходы ServerSkif): состояние, вкл/выкл, переключение, 9 программ, время
### Изменения 0.6.3
- 🐞 **Исправлен пустой список шлейфов в настройках** («Выбор шлейфов» — ни одной строки).
  - Пустой ответ опроса ARM больше **не кэшируется** (раньше пустой список «залипал» на 10 минут — как раз после рестарта HA/ARM).
  - Добавлен **автоматический повтор** опроса (1 раз), клиенты опроса корректно **закрываются** (нет утечки WS-соединений).
  - Если опрос всё же не удался — показываются **ранее выбранные шлейфы** и понятное сообщение вместо пустого списка.
### Изменения 0.6.2
- 🖼️ **Фирменный знак SecurARM** (щит с шестернёй и замком, логотип автора) в `brand/` — icon/logo + тёмные варианты и `@2x`.
### Изменения 0.6.1
- 🏷️ **Переименование в SecurARM:** отображаемое имя интеграции и устройства — **SecurARM Sensor**, обновлены логотипы/иконки (`brand/`, вордмарк **SECURARM**).
- ⚠️ Домен `techlan_sensor`, `unique_id` и все `entity_id` **не изменены** — история и автоматизации сохраняются.
### Изменения 0.6.0
- **Управление реле** (управляемыми выходами ServerSkif). Решение проекта: управление **реле** — здесь,
  управление **разделами** (arm/disarm) — по-прежнему только в `techlan_ops`.
- Протокол: `getListDevices` → `getListRelay` → `getRelayDescription`/`getRelayState`;
  `controlRelay_Inv` (переключить); `controlRelay` (программа). `rl = (device << 8) | relay_number`.
- Состояния реле: **Включено / Выключено / Мигает**. Программы (9): сброс, вкл, выкл, вкл-на-время,
  выкл-на-время, мигание из вкл/выкл, мигание-на-время. Поле `time` — секунды (в протокол 0.125 c).
- На каждое выбранное реле — **5 сущностей**: `sensor` (состояние), `switch` (вкл/выкл),
  `button` (переключить), `select` (программа), `number` (время).
- Настройки: сначала выбираются ПКУ (лёгкий запрос), затем реле только этих ПКУ (полный инвентарь большой).
- Команда отправляется вместе с пакетом `userId`. Миграция схемы (minor 4) добавляет `selected_relays`,
  `relay_time`, `relay_program` — существующие сущности не пересоздаются.
### Изменения 0.5.0
- **Только чтение климата** — интеграция больше не содержит управляющих сервисов/кнопок (управление ОПС — в `techlan_ops`).
- **`number`-сущности:** `temperature_scale`/`offset`, `humidity_scale`/`offset`, `temperature_alarm_low`/`high`.
- Климат считается как `(temperature|adc) × scale + offset`; тревога по температуре — по коду 206 и порогам.
- **Постоянное read-only WebSocket-соединение** с реконнектом.
- **Диагностика**, **Repairs**, enum-классы, миграция схемы; **фирменный брендинг** (светлая/тёмная тема).
### Установка
1. Скопируйте папку `custom_components/techlan_sensor/` в каталог `custom_components/` конфигурации Home Assistant.
2. Перезапустите Home Assistant.
3. Настройки → Устройства и службы → Добавить интеграцию → **SecurARM Sensor**.
> Установка через HACS: добавьте репозиторий `https://github.com/bezuglyy/techlan_sensor` как Custom repository (категория Integration).
---
## Description
ServerSkif (Techlan) security loop sensors and **relay control**.
### Features
- Full configuration via UI (config flow)
- Climate: loop ADC, temperature/humidity with scale/offset and alarm thresholds
- **Relays** (ServerSkif controllable outputs): state, on/off, toggle, 9 programs, duration
### Changes 0.6.3
- 🐞 **Fixed empty loop list in settings** (“Select loops” showed nothing): empty ARM response is no longer cached (it used to stick for 10 minutes right after an HA/ARM restart), a retry was added, discovery clients are closed, and the previously selected loops are shown with a clear message when the query fails.
### Changes 0.6.2
- 🖼️ **Фирменный знак SecurARM** (щит с шестернёй и замком, логотип автора) в `brand/` — icon/logo + тёмные варианты и `@2x`.
### Changes 0.6.1
- 🏷️ **Renamed to SecurARM:** integration and device display name — **SecurARM Sensor**; brand assets regenerated with the **SECURARM** wordmark.
- ⚠️ Domain `techlan_sensor`, `unique_id`s and all `entity_id`s are unchanged.
### Changes 0.6.0
- Relay control (5 entities per relay: state sensor, switch, toggle button, program select, duration number).
- Part control (arm/disarm) remains in `techlan_ops` only.
### Installation
1. Copy the `custom_components/techlan_sensor/` folder into the `custom_components/` directory of your Home Assistant configuration.
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **SecurARM Sensor**.
> HACS: add `https://github.com/bezuglyy/techlan_sensor` as a Custom repository (category Integration).
---
**Автор / Author:**
![Bezuglyj E.N.](logo-bezuglyj.png)
## License / Лицензия
MIT
