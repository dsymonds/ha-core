"""Support for Jewish calendar sensors."""

from __future__ import annotations

from datetime import date as Date
import logging
from typing import Any, cast

from hdate import HDate, HebrewDate, htables
from hdate.zmanim import Zmanim

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LANGUAGE, CONF_LOCATION, SUN_EVENT_SUNSET
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.sun import get_astral_event_date
import homeassistant.util.dt as dt_util

from .const import (
    CONF_CANDLE_LIGHT_MINUTES,
    CONF_DIASPORA,
    CONF_HAVDALAH_OFFSET_MINUTES,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

INFO_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="date",
        name="Date",
        icon="mdi:star-david",
        translation_key="hebrew_date",
    ),
    SensorEntityDescription(
        key="weekly_portion",
        name="Parshat Hashavua",
        icon="mdi:book-open-variant",
        device_class=SensorDeviceClass.ENUM,
    ),
    SensorEntityDescription(
        key="holiday",
        name="Holiday",
        icon="mdi:calendar-star",
        device_class=SensorDeviceClass.ENUM,
    ),
    SensorEntityDescription(
        key="omer_count",
        name="Day of the Omer",
        icon="mdi:counter",
    ),
    SensorEntityDescription(
        key="daf_yomi",
        name="Daf Yomi",
        icon="mdi:book-open-variant",
    ),
)

TIME_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="first_light",
        name="Alot Hashachar",  # codespell:ignore alot
        icon="mdi:weather-sunset-up",
    ),
    SensorEntityDescription(
        key="talit",
        name="Talit and Tefillin",
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="sunrise",
        name="Hanetz Hachama",
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="gra_end_shma",
        name='Latest time for Shma Gr"a',
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="mga_end_shma",
        name='Latest time for Shma MG"A',
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="gra_end_tfila",
        name='Latest time for Tefilla Gr"a',
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="mga_end_tfila",
        name='Latest time for Tefilla MG"A',
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="midday",
        name="Chatzot Hayom",
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="big_mincha",
        name="Mincha Gedola",
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="small_mincha",
        name="Mincha Ketana",
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="plag_mincha",
        name="Plag Hamincha",
        icon="mdi:weather-sunset-down",
    ),
    SensorEntityDescription(
        key="sunset",
        name="Shkia",
        icon="mdi:weather-sunset",
    ),
    SensorEntityDescription(
        key="first_stars",
        name="T'set Hakochavim",
        icon="mdi:weather-night",
    ),
    SensorEntityDescription(
        key="three_stars",
        name="T'set Hakochavim, 3 stars",
        icon="mdi:weather-night",
    ),
    SensorEntityDescription(
        key="upcoming_shabbat_candle_lighting",
        name="Upcoming Shabbat Candle Lighting",
        icon="mdi:candle",
    ),
    SensorEntityDescription(
        key="upcoming_shabbat_havdalah",
        name="Upcoming Shabbat Havdalah",
        icon="mdi:weather-night",
    ),
    SensorEntityDescription(
        key="upcoming_candle_lighting",
        name="Upcoming Candle Lighting",
        icon="mdi:candle",
    ),
    SensorEntityDescription(
        key="upcoming_havdalah",
        name="Upcoming Havdalah",
        icon="mdi:weather-night",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Jewish calendar sensors ."""
    entry = hass.data[DOMAIN][config_entry.entry_id]
    sensors = [
        JewishCalendarSensor(config_entry.entry_id, entry, description)
        for description in INFO_SENSORS
    ]
    sensors.extend(
        JewishCalendarTimeSensor(config_entry.entry_id, entry, description)
        for description in TIME_SENSORS
    )

    async_add_entities(sensors)


class JewishCalendarSensor(SensorEntity):
    """Representation of an Jewish calendar sensor."""

    def __init__(
        self,
        entry_id: str,
        data: dict[str, Any],
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the Jewish calendar sensor."""
        self.entity_description = description
        self._attr_name = f"{DEFAULT_NAME} {description.name}"
        self._attr_unique_id = f"{entry_id}-{description.key}"
        self._location = data[CONF_LOCATION]
        self._hebrew = data[CONF_LANGUAGE] == "hebrew"
        self._candle_lighting_offset = data[CONF_CANDLE_LIGHT_MINUTES]
        self._havdalah_offset = data[CONF_HAVDALAH_OFFSET_MINUTES]
        self._diaspora = data[CONF_DIASPORA]
        self._attrs: dict[str, str] = {}

    async def async_update(self) -> None:
        """Update the state of the sensor."""
        now = dt_util.now()
        _LOGGER.debug("Now: %s Location: %r", now, self._location)

        today = now.date()
        event_date = get_astral_event_date(self.hass, SUN_EVENT_SUNSET, today)

        if event_date is None:
            _LOGGER.error("Can't get sunset event date for %s", today)
            return

        sunset = dt_util.as_local(event_date)

        _LOGGER.debug("Now: %s Sunset: %s", now, sunset)

        daytime_date = HDate(today, diaspora=self._diaspora, hebrew=self._hebrew)

        # The Jewish day starts after darkness (called "tzais") and finishes at
        # sunset ("shkia"). The time in between is a gray area
        # (aka "Bein Hashmashot"  # codespell:ignore
        # - literally: "in between the sun and the moon").

        # For some sensors, it is more interesting to consider the date to be
        # tomorrow based on sunset ("shkia"), for others based on "tzais".
        # Hence the following variables.
        after_tzais_date = after_shkia_date = daytime_date
        today_times = self.make_zmanim(today)

        if now > sunset:
            after_shkia_date = daytime_date.next_day

        if today_times.havdalah and now > today_times.havdalah:
            after_tzais_date = daytime_date.next_day

        self._attr_native_value = self.get_state(
            daytime_date, after_shkia_date, after_tzais_date
        )
        _LOGGER.debug(
            "New value for %s: %s", self.entity_description.key, self._attr_native_value
        )

    def make_zmanim(self, date: Date) -> Zmanim:
        """Create a Zmanim object."""
        return Zmanim(
            date=date,
            location=self._location,
            candle_lighting_offset=self._candle_lighting_offset,
            havdalah_offset=self._havdalah_offset,
            hebrew=self._hebrew,
        )

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the state attributes."""
        return self._attrs

    def get_state(
        self, daytime_date: HDate, after_shkia_date: HDate, after_tzais_date: HDate
    ) -> Any | None:
        """For a given type of sensor, return the state."""
        # Terminology note: by convention in py-libhdate library, "upcoming"
        # refers to "current" or "upcoming" dates.
        if self.entity_description.key == "date":
            hdate = cast(HebrewDate, after_shkia_date.hdate)
            month = htables.MONTHS[hdate.month.value - 1]
            self._attrs = {
                "hebrew_year": hdate.year,
                "hebrew_month_name": month.hebrew if self._hebrew else month.english,
                "hebrew_day": hdate.day,
            }
            return after_shkia_date.hebrew_date
        if self.entity_description.key == "weekly_portion":
            self._attr_options = [
                (p.hebrew if self._hebrew else p.english) for p in htables.PARASHAOT
            ]
            # Compute the weekly portion based on the upcoming shabbat.
            return after_tzais_date.upcoming_shabbat.parasha
        if self.entity_description.key == "holiday":
            self._attrs = {
                "id": after_shkia_date.holiday_name,
                "type": after_shkia_date.holiday_type.name,
                "type_id": after_shkia_date.holiday_type.value,
            }
            self._attr_options = [
                h.description.hebrew.long if self._hebrew else h.description.english
                for h in htables.HOLIDAYS
            ]

            return after_shkia_date.holiday_description
        if self.entity_description.key == "omer_count":
            return after_shkia_date.omer_day
        if self.entity_description.key == "daf_yomi":
            return daytime_date.daf_yomi

        return None


class JewishCalendarTimeSensor(JewishCalendarSensor):
    """Implement attributes for sensors returning times."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def get_state(
        self, daytime_date: HDate, after_shkia_date: HDate, after_tzais_date: HDate
    ) -> Any | None:
        """For a given type of sensor, return the state."""
        if self.entity_description.key == "upcoming_shabbat_candle_lighting":
            times = self.make_zmanim(
                after_tzais_date.upcoming_shabbat.previous_day.gdate
            )
            return times.candle_lighting
        if self.entity_description.key == "upcoming_candle_lighting":
            times = self.make_zmanim(
                after_tzais_date.upcoming_shabbat_or_yom_tov.first_day.previous_day.gdate
            )
            return times.candle_lighting
        if self.entity_description.key == "upcoming_shabbat_havdalah":
            times = self.make_zmanim(after_tzais_date.upcoming_shabbat.gdate)
            return times.havdalah
        if self.entity_description.key == "upcoming_havdalah":
            times = self.make_zmanim(
                after_tzais_date.upcoming_shabbat_or_yom_tov.last_day.gdate
            )
            return times.havdalah

        times = self.make_zmanim(dt_util.now()).zmanim
        return times[self.entity_description.key]
