# Techlan Sensor

Home Assistant custom integration for read-only monitoring of selected ServerSkif loops through the Techlan ARM WebSocket proxy.

## Features

- Poll only the selected loops (`pku:part:sh`).
- Raw ADC sensor for each selected loop.
- Optional temperature sensor with configurable `ADC × scale + offset` calibration.
- Optional humidity sensor with configurable `ADC × scale + offset` calibration.
- Temperature alarm binary sensor based on the ServerSkif loop state.
- Direct temperature/humidity values are used when ServerSkif returns values explicitly labelled with `°C` or `%`.
- No ordinary loop state entities are created, so `Снят/Взят` states do not clutter the dashboard.
- ARM URL, WebSocket path, credentials, polling interval and selected loops are configured from the Home Assistant UI.

## Installation

Copy `custom_components/techlan_sensor` to `/config/custom_components/techlan_sensor/`, restart Home Assistant, then add **Techlan Sensor** from Settings → Devices & services.

## Temperature and humidity setup

In the integration options select the required loop in **Температурные ШС** or **ШС влажности**. The loop is automatically added to the polling set.

Calibration uses:

```text
value = adc × scale + offset
```

The default coefficients are placeholders (`scale=1`, `offset=0`) and must be calibrated against the installed device. Raw ADC and the original ServerSkif value remain available as entity attributes.

## Requirements

- Home Assistant 2026.7 or newer
- ARM WebSocket proxy with `/skif-ws`
- `websocket-client >= 1.8.0`

## Safety

This integration performs read-only monitoring. It does not arm or disarm sections and does not include credentials or Config Entry data.
