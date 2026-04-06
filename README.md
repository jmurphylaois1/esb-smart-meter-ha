# ESB Smart Meter for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/jmurphylaois1/esb-smart-meter-ha.svg)](https://github.com/jmurphylaois1/esb-smart-meter-ha/releases)

Home Assistant integration for ESB Networks (Ireland) smart meters. Downloads your half-hourly electricity consumption data and adds it to the Energy Dashboard with full historical data going back up to 2 years.

## Features

- Full historical consumption data (up to 2 years) in the Energy Dashboard
- Daily and monthly bar charts out of the box
- Updates every 6 hours
- Handles ESB Networks' Azure B2C login flow automatically
- Session caching to minimise login frequency (CAPTCHA rate limit protection)

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations → ⋮ → Custom repositories**
3. Add `https://github.com/jmurphylaois1/esb-smart-meter-ha` as an **Integration**
4. Search for **ESB Smart Meter** and install
5. Restart Home Assistant

### Manual

Copy `custom_components/esb_smart_meter/` to your HA `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **ESB Smart Meter**
3. Enter your credentials:

| Field | Description |
|-------|-------------|
| Email address | Your myaccount.esbnetworks.ie login email |
| Password | Your ESB Networks password |
| MPRN | Your 11-digit Meter Point Reference Number |

Your MPRN is on your electricity bill or at [myaccount.esbnetworks.ie](https://myaccount.esbnetworks.ie) under your meter details.

## Energy Dashboard

After the first successful update, your consumption data will appear at **Settings → Dashboards → Energy → Add consumption → Pick a statistical sensor** — select **ESB Smart Meter Consumption**.

Historical data (up to 2 years) is imported on first run.

## Dashboard Cards

Find all card examples in [`examples/dashboard_cards.yaml`](examples/dashboard_cards.yaml).

Replace `YOUR_MPRN` with your 11-digit MPRN (digits only, no spaces).

### Daily Consumption Bar Chart

Shows kWh consumed each day for the last 30 days.

```yaml
type: statistics-graph
title: Daily Consumption — Last 30 Days
entities:
  - entity: esb_smart_meter:consumption_YOUR_MPRN
    name: Grid Import
stat_types:
  - change
period: day
days_to_show: 30
chart_type: bar
```

### Monthly Consumption Bar Chart

```yaml
type: statistics-graph
title: Monthly Consumption
entities:
  - entity: esb_smart_meter:consumption_YOUR_MPRN
    name: Grid Import
stat_types:
  - change
period: month
days_to_show: 365
chart_type: bar
```

### Yesterday's Usage (entity card)

```yaml
type: entity
entity: sensor.esb_smart_meter_consumption
name: Yesterday's Usage
icon: mdi:transmission-tower
```

## Notes

- ESB Networks rate-limits logins (~2 per IP per 24 hours). The integration caches sessions for 12 hours to minimise login attempts.
- If you see `CAPTCHA detected` in the logs, the integration will retry automatically on the next 6-hour cycle.
- Data appears in the Energy Dashboard after the first successful update (may take a few minutes on first run due to the volume of historical data).

## Troubleshooting

**No data after installation**

Check **Settings → System → Logs** for `ESB:` log entries. Common causes:
- Incorrect credentials — re-enter via Settings → Devices & Services → ESB Smart Meter → Configure
- CAPTCHA rate limit — wait 24 hours and restart the integration

**Data stops updating**

Your ESB session may have expired. Restart the integration or wait for the next 6-hour cycle.

## License

MIT
