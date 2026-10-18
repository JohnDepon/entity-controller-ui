"""Restart/reload behaviour and time constraints."""
from datetime import timedelta
from pytest_homeassistant_custom_component.common import async_mock_service

from .conftest import EC, LIGHT, MOTION, OVERRIDE, advance, set_state, setup_controller, state


async def test_reload_resumes_active_timer_without_switching(hass, freezer, entities):
    entry = await setup_controller(hass, freezer, delay=60)
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    assert state(hass) == "active_timer"

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await advance(hass, freezer, 2)
    # Still controlling the light, which was not switched off by the reload.
    assert state(hass) == "active_timer"
    assert state(hass, LIGHT) == "on"
    await advance(hass, freezer, 61)
    assert state(hass) == "idle"
    assert state(hass, LIGHT) == "off"


async def test_reload_keeps_blocked_light_on(hass, freezer, entities):
    entry = await setup_controller(hass, freezer)
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": LIGHT}, blocking=True)
    await set_state(hass, MOTION, "on")
    assert state(hass) == "blocked"

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await advance(hass, freezer, 2)
    assert state(hass) == "blocked"
    assert state(hass, LIGHT) == "on"


async def test_reload_does_not_switch_off_manual_light(hass, freezer, entities):
    entry = await setup_controller(hass, freezer)
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": LIGHT}, blocking=True)
    await hass.async_block_till_done()
    assert state(hass) == "idle"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await advance(hass, freezer, 2)
    assert state(hass) == "idle"
    assert state(hass, LIGHT) == "on"


async def test_override_on_at_startup(hass, freezer, entities):
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": OVERRIDE}, blocking=True)
    await setup_controller(hass, freezer, overrides=[OVERRIDE])
    assert state(hass) == "overridden"


async def test_time_constraints(hass, freezer, entities):
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-06-01 12:00:00+00:00")
    await setup_controller(
        hass,
        freezer,
        start_time="18:00:00",
        end_time="23:00:00",
        behaviours={"on_enter_constrained": "off"},
        delay=6 * 3600,
    )
    assert state(hass) == "constrained"
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    assert state(hass, LIGHT) == "off"

    await advance(hass, freezer, 6 * 3600)  # 18:00
    assert state(hass) == "idle"
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    assert state(hass, LIGHT) == "on"

    turn_off = async_mock_service(hass, "input_boolean", "turn_off")
    await advance(hass, freezer, 5 * 3600)  # 23:00, light still on (delay 6h)
    assert state(hass) == "constrained"
    # on_enter_constrained ran exactly once (the original ran it twice).
    assert len(turn_off) == 1
    attrs = hass.states.get(EC).attributes
    assert str(attrs["start_time"]) == "2026-06-02 18:00:00"
    assert str(attrs["end_time"]) == "2026-06-02 23:00:00"


async def test_start_time_with_light_on_blocks(hass, freezer, entities):
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-06-01 12:00:00+00:00")
    await setup_controller(hass, freezer, start_time="18:00:00", end_time="23:00:00")
    assert state(hass) == "constrained"
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": LIGHT}, blocking=True)
    await advance(hass, freezer, 6 * 3600)
    assert state(hass) == "blocked"


async def test_override_switched_on_while_constrained(hass, freezer, entities):
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-06-01 12:00:00+00:00")
    await setup_controller(hass, freezer, start_time="18:00:00", end_time="23:00:00", overrides=[OVERRIDE])
    assert state(hass) == "constrained"
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": LIGHT}, blocking=True)
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": OVERRIDE}, blocking=True)
    await advance(hass, freezer, 6 * 3600)
    assert state(hass) == "overridden"


async def test_reload_keeps_delayed_fan_min_time(hass, freezer, entities):
    from .conftest import FAN
    from .test_controller import DELAYED

    entry = await setup_controller(hass, freezer, **DELAYED)
    await set_state(hass, MOTION, "on")
    await advance(hass, freezer, 121)  # fan on, minimum runs until +300 s
    await set_state(hass, MOTION, "off")  # light off, fan keeps running
    assert state(hass, FAN) == "on"

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await advance(hass, freezer, 2)
    assert state(hass, FAN) == "on"
    await advance(hass, freezer, 296)
    assert state(hass, FAN) == "on"
    await advance(hass, freezer, 4)  # minimum over: turned off after the reload
    assert state(hass, FAN) == "off"


async def test_reload_keeps_delayed_fan_while_still_there(hass, freezer, entities):
    from .conftest import FAN
    from .test_controller import DELAYED

    entry = await setup_controller(hass, freezer, **DELAYED)
    await set_state(hass, MOTION, "on")
    await advance(hass, freezer, 121)  # fan on
    await advance(hass, freezer, 400)  # minimum over, still there

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await advance(hass, freezer, 2)
    assert state(hass, FAN) == "on"
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 61)  # resumed light timer runs out
    assert state(hass, LIGHT) == "off"
    assert state(hass, FAN) == "off"


async def test_restart_restores_delayed_fan(hass, freezer, entities):
    from homeassistant.core import State
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import (
        mock_restore_cache_with_extra_data,
    )

    from .conftest import FAN
    from .test_controller import DELAYED

    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": FAN}, blocking=True)
    until = (dt_util.utcnow() + timedelta(seconds=100)).isoformat()
    mock_restore_cache_with_extra_data(
        hass, [(State(EC, "idle"), {"delayed_running": [FAN], "delayed_min_until": until})]
    )
    await setup_controller(hass, freezer, **DELAYED)
    assert state(hass, FAN) == "on"
    await advance(hass, freezer, 99)
    assert state(hass, FAN) == "off"
