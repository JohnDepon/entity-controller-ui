"""Shared fixtures for the Entity Controller tests."""
from __future__ import annotations

from datetime import timedelta
import sys
from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.entity_controller.const import DOMAIN
from custom_components.entity_controller.options import default_options

pytest_plugins = "pytest_homeassistant_custom_component"

LIGHT = "input_boolean.light"
LIGHT2 = "input_boolean.light2"
MOTION = "binary_sensor.motion"
PRESENCE = "binary_sensor.presence"
OVERRIDE = "input_boolean.override"
FAN = "input_boolean.fan"
EC = "entity_controller.test"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom integrations in all tests."""
    yield


if sys.platform == "win32":
    # The Windows event loop creates its internal wake-up pipe with a localhost
    # socket pair, which the Home Assistant test harness blocks. Home Assistant
    # does not run on Windows; this only lets developers run the tests there.
    import pytest_socket

    pytest_socket.disable_socket = lambda *args, **kwargs: None


@pytest.fixture
async def entities(hass: HomeAssistant) -> None:
    """Controlled entities (input_booleans) and sensors."""
    assert await async_setup_component(
        hass,
        "input_boolean",
        {"input_boolean": {"light": None, "light2": None, "override": None, "fan": None}},
    )
    hass.states.async_set(MOTION, "off")
    hass.states.async_set(PRESENCE, "off")
    await hass.async_block_till_done()


async def advance(hass: HomeAssistant, freezer, seconds: float) -> None:
    """Move time forward and run everything that became due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def set_state(hass: HomeAssistant, entity_id: str, state: str, **attrs) -> None:
    hass.states.async_set(entity_id, state, attrs or None)
    await hass.async_block_till_done()


async def setup_controller(
    hass: HomeAssistant, freezer, title: str = "Test", **overrides: Any
) -> MockConfigEntry:
    """Create a controller config entry and wait until it monitors."""
    options = default_options()
    options.update({"sensors": [MOTION], "entities": [LIGHT], "delay": 60})
    options.update(overrides)
    entry = MockConfigEntry(domain=DOMAIN, title=title, data={}, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # Controllers start monitoring shortly after being loaded.
    await advance(hass, freezer, 2)
    return entry


def state(hass: HomeAssistant, entity_id: str = EC) -> str | None:
    current = hass.states.get(entity_id)
    return current.state if current else None
