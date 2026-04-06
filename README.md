# ESB Smart Meter for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

Home Assistant integration for ESB Networks (Ireland) smart meters. Downloads your half-hourly electricity consumption data and adds it to the Energy Dashboard with full historical data going back up to 2 years.

## Features

- Full historical consumption data (up to 2 years) in the Energy Dashboard
- Updates every 6 hours
- Handles ESB Networks' Azure B2C login flow automatically
- Session caching to minimise login frequency (CAPTCHA rate limit protection)

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to Integrations → ⋮ → Custom repositories
3. Add `https://github.com/jmurphylaois1/esb-smart-meter-ha` as an Integration
4. Search for "ESB Smart Meter" and install
5. Restart Home Assistant

### Manual

Copy `custom_components/esb_smart_meter/` to your HA `config/custom_components/` directory and restart.

## Configuration

1. Go to Settings → Devices & Services → Add Integration
2. Search for "ESB Smart Meter"
3. Enter your myaccount.esbnetworks.ie email, password, and MPRN

Your MPRN (Meter Point Reference Number) is the 11-digit number on your ESB Networks account or electricity bill.

## Notes

- ESB Networks rate-limits logins (~2 per IP per 24 hours). The integration caches sessions for 12 hours to minimise login attempts.
- Data appears in Settings → Dashboards → Energy after the first successful update.
