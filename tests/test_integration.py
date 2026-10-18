"""Entity Controller as a regular integration: one entry and device per controller."""
import json
from pathlib import Path

import pytest

from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.entity_controller.const import DOMAIN

from .conftest import EC, LIGHT, MOTION, advance, set_state, setup_controller, state

MANIFEST = Path(__file__).parent.parent / "custom_components" / DOMAIN / "manifest.json"


def controller_device(hass, entry):
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return devices[0] if devices else None


def test_manifest_is_a_regular_integration():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["integration_type"] == "service"
    assert manifest["config_flow"] is True


async def test_controller_device_and_entities(hass, freezer, entities):
    entry = await setup_controller(hass, freezer)
    device = controller_device(hass, entry)
    assert device is not None
    assert device.identifiers == {(DOMAIN, entry.entry_id)}
    assert device.name == "Test"
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.config_entries == {entry.entry_id}

    entity_ids = {
        e.entity_id for e in er.async_entries_for_device(er.async_get(hass), device.id)
    }
    assert entity_ids == {
        EC,
        "button.test_activate",
        "button.test_clear_block",
        "button.test_enable_block",
        "switch.test_stay_mode",
    }
    # The controller entity is named after its device.
    assert hass.states.get(EC).attributes["friendly_name"] == "Test"


async def test_buttons(hass, freezer, entities):
    await setup_controller(hass, freezer, delay=60)

    async def press(entity_id):
        await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
        await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await press("button.test_clear_block")  # not blocked

    await press("button.test_activate")
    assert state(hass) == "active_timer"
    assert state(hass, LIGHT) == "on"

    await press("button.test_enable_block")
    assert state(hass) == "blocked"
    await press("button.test_clear_block")
    assert state(hass) == "active_timer"


async def test_stay_mode_switch_saves_option_without_reload(hass, freezer, entities):
    entry = await setup_controller(hass, freezer, delay=60)
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    expires_at = hass.states.get(EC).attributes["expires_at"]
    controller = entry.runtime_data.entity

    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.test_stay_mode"}, blocking=True)
    await hass.async_block_till_done()
    assert entry.options["stay_mode"] is True
    assert state(hass, "switch.test_stay_mode") == "on"
    # Applied in place: same controller instance, timer untouched.
    assert entry.runtime_data.entity is controller
    assert hass.states.get(EC).attributes["expires_at"] == expires_at

    # Takes effect from the next activation.
    await advance(hass, freezer, 61)
    assert state(hass) == "idle"
    await set_state(hass, MOTION, "on")
    assert state(hass) == "active_stay_on"

    # The action does the same.
    await hass.services.async_call("entity_controller", "disable_stay_mode", {"entity_id": EC}, blocking=True)
    await hass.async_block_till_done()
    assert entry.options["stay_mode"] is False
    assert state(hass, "switch.test_stay_mode") == "off"


async def test_stay_mode_from_options_flow(hass, freezer, entities):
    entry = await setup_controller(hass, freezer)
    controller = entry.runtime_data.entity
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "timer"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"delay": 60, "stay_mode": True, "backoff": False}
    )
    await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "save"})
    await hass.async_block_till_done()
    assert entry.runtime_data.entity is controller  # no reload needed
    assert state(hass, "switch.test_stay_mode") == "on"


async def test_rename_updates_device_and_names(hass, freezer, entities):
    entry = await setup_controller(hass, freezer)
    hass.config_entries.async_update_entry(entry, title="Hallway")
    await hass.async_block_till_done()
    await advance(hass, freezer, 2)
    device = controller_device(hass, entry)
    assert device.name == "Hallway"
    # Entity ids are kept, so automations keep working.
    assert hass.states.get(EC).attributes["friendly_name"] == "Hallway"
    assert hass.states.get("button.test_activate").attributes["friendly_name"] == "Hallway Activate"


async def test_disable_and_remove_entry(hass, freezer, entities):
    entry = await setup_controller(hass, freezer)
    await set_state(hass, MOTION, "on")

    assert await hass.config_entries.async_set_disabled_by(
        entry.entry_id, ConfigEntryDisabler.USER
    )
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    await advance(hass, freezer, 600)
    assert state(hass, LIGHT) == "on"  # a disabled controller does nothing

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert controller_device(hass, entry) is None
    assert er.async_get(hass).async_get(EC) is None
    assert hass.states.get(EC) is None


def test_translations_only_use_simple_placeholders():
    """The frontend parses UI texts as ICU messages: a literal brace (e.g. a
    template example) breaks the whole text ("Translation error")."""
    import re

    path = MANIFEST.parent / "translations" / "en.json"

    def texts(node):
        if isinstance(node, dict):
            for value in node.values():
                yield from texts(value)
        elif isinstance(node, str):
            yield node

    for text in texts(json.loads(path.read_text(encoding="utf-8"))):
        assert re.sub(r"\{\w+\}", "", text).count("{") == 0, text
        assert re.sub(r"\{\w+\}", "", text).count("}") == 0, text


async def test_service_data_form_gets_template_example(hass, entities):
    from homeassistant import config_entries

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "X", "sensors": [MOTION], "sensor_type": "event", "delay": 10}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "service_data"})
    assert "{{" in result["description_placeholders"]["template_example"]
