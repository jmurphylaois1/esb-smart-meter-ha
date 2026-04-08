import asyncio
import logging
from datetime import datetime, timedelta, timezone

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .api import ESBNetworksAPI, parse_csv
from .const import CONF_MPRN, CONF_PASSWORD, CONF_USERNAME, DOMAIN, UPDATE_INTERVAL_HOURS

_LOGGER = logging.getLogger(DOMAIN)

UTC = timezone.utc


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    mprn_clean = entry.data[CONF_MPRN].replace(" ", "").strip()
    api = ESBNetworksAPI(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_MPRN],
        cache_path=hass.config.path(".storage", "esb_session_cache.json"),
    )
    sensor = ESBSmartMeterSensor(api, mprn_clean, entry.entry_id)
    async_add_entities([sensor])


class ESBSmartMeterSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "ESB Smart Meter Consumption"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:lightning-bolt"
    _attr_should_poll = False

    def __init__(self, api: ESBNetworksAPI, mprn: str, entry_id: str):
        self._api = api
        self._mprn = mprn  # already stripped
        self._attr_unique_id = f"{DOMAIN}_{mprn}"
        self._attr_native_value = None
        self._remove_listener = None
        self._last_update: datetime | None = None

    @property
    def extra_state_attributes(self):
        return {
            "mprn": self._mprn,
            "last_update": self._last_update.isoformat() if self._last_update else None,
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        _LOGGER.info("ESB: sensor added to hass, scheduling updates every %dh", UPDATE_INTERVAL_HOURS)
        await self._do_update()
        self._remove_listener = async_track_time_interval(
            self.hass,
            lambda _: asyncio.ensure_future(self._do_update()),
            timedelta(hours=UPDATE_INTERVAL_HOURS),
        )

    async def async_will_remove_from_hass(self):
        if self._remove_listener:
            self._remove_listener()

    async def async_update(self):
        """Called by update_entity service — delegate to _do_update."""
        await self._do_update()

    @property
    def statistic_id(self):
        return f"{DOMAIN}:consumption_{self._mprn}"

    async def _do_update(self):
        _LOGGER.info("ESB: starting data fetch")
        loop = asyncio.get_running_loop()

        try:
            csv_text = await loop.run_in_executor(None, self._api.download_csv)
        except Exception as e:
            _LOGGER.error("ESB: download failed: %s", e)
            return

        if not csv_text:
            _LOGGER.error("ESB: no CSV data returned")
            return

        datapoints = await loop.run_in_executor(None, parse_csv, csv_text)
        if not datapoints:
            _LOGGER.error("ESB: no datapoints parsed from CSV")
            return

        # Today's consumption (native sensor value)
        today = datetime.now(UTC).date()
        today_kwh = sum(
            dp["kwh"] for dp in datapoints
            if dp["dt"].date() == today
        )
        yesterday_kwh = sum(
            dp["kwh"] for dp in datapoints
            if dp["dt"].date() == (today - timedelta(days=1))
        )
        self._attr_native_value = round(yesterday_kwh, 3)  # yesterday (most recent complete day)
        self._last_update = datetime.now(UTC)
        self.async_write_ha_state()

        # Write long-term statistics (for Energy Dashboard)
        # Always start from 0 — the full dataset is downloaded every time
        accumulated = 0.0

        # Group into hourly buckets
        hourly: dict[datetime, float] = {}
        for dp in datapoints:
            bucket = dp["dt"].replace(minute=0, second=0, microsecond=0)
            hourly[bucket] = hourly.get(bucket, 0.0) + dp["kwh"]

        stat_data = []
        for dt in sorted(hourly.keys()):
            accumulated += hourly[dt]
            stat_data.append(StatisticData(start=dt, state=hourly[dt], sum=accumulated))

        meta = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name="ESB Smart Meter Consumption",
            source=DOMAIN,
            statistic_id=self.statistic_id,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

        async_add_external_statistics(self.hass, meta, stat_data)
        _LOGGER.info(
            "ESB: wrote %d hourly stat entries. Yesterday: %.3f kWh, today so far: %.3f kWh",
            len(stat_data), yesterday_kwh, today_kwh,
        )
