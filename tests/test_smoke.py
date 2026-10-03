"""The integration loads, creates its entity and unloads cleanly."""
from homeassistant.config_entries import ConfigEntryState

from .conftest import EC, LIGHT, MOTION, advance, set_state, setup_controller, state


async def test_load_unload(hass, freezer, entities):
    entry = await setup_controller(hass, freezer)
    assert entry.state is ConfigEntryState.LOADED
    assert state(hass) == "idle"

    await set_state(hass, MOTION, "on")
    assert state(hass) == "active_timer"
    assert state(hass, LIGHT) == "on"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    # Timers were cancelled: nothing happens when the delay passes.
    await advance(hass, freezer, 120)
    assert state(hass, LIGHT) == "on"
    assert hass.states.get(EC).state == "unavailable"


async def test_diagnostics(hass, freezer, entities):
    from custom_components.entity_controller.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = await setup_controller(hass, freezer)
    await set_state(hass, MOTION, "on")
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entity_id"] == EC
    assert diag["state"] == "active_timer"
    assert diag["watched_entity_states"] == {MOTION: "on", LIGHT: "on"}
