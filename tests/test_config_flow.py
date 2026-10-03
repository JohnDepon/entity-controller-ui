"""UI configuration: config flow, options flow and YAML import."""
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.entity_controller.const import DOMAIN

from .conftest import EC, LIGHT, LIGHT2, MOTION, PRESENCE, advance, set_state, setup_controller, state


async def _start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_create_controller(hass, freezer, entities):
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Hallway", "sensors": [MOTION], "sensor_type": "duration", "entities": [LIGHT], "delay": 30},
    )
    assert result["type"] is FlowResultType.MENU
    assert "finish" in result["menu_options"]

    # Optionally configure more before creating the controller.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "triggers"})
    assert result["step_id"] == "triggers"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "sensors": [MOTION],
            "sensor_type": "duration",
            "sensor_resets_timer": True,
            "hold_sensors": [PRESENCE],
            "max_hold_time": 7200,
        },
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "finish"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hallway"
    options = result["options"]
    assert options["sensors"] == [MOTION]
    assert options["hold_sensors"] == [PRESENCE]
    assert options["max_hold_time"] == 7200
    assert options["sensor_type"] == "duration"
    assert options["sensor_resets_timer"] is True
    assert options["entities"] == [LIGHT]
    assert options["delay"] == 30
    await hass.async_block_till_done()

    await advance(hass, freezer, 2)
    assert state(hass, "entity_controller.hallway") == "idle"
    await set_state(hass, MOTION, "on")
    assert state(hass, LIGHT) == "on"


async def test_user_step_errors(hass, entities):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": " ", "sensors": [], "sensor_type": "event", "delay": 10}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"name": "name_required", "sensors": "no_sensors"}


async def test_finish_requires_entities(hass, entities):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "X", "sensors": [MOTION], "sensor_type": "event", "delay": 10}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "finish"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "entities"
    assert result["errors"] == {"base": "no_entities"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"trigger_on_activate": ["script.x"]})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "finish"})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_section_validation(hass, entities):
    result = await _start(hass)
    flow_id = result["flow_id"]
    await hass.config_entries.flow.async_configure(
        flow_id, {"name": "X", "sensors": [MOTION], "sensor_type": "event", "entities": [LIGHT], "delay": 10}
    )

    await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": "constraints"})
    result = await hass.config_entries.flow.async_configure(flow_id, {"start_time": "25:00", "end_time": "sunrise"})
    assert result["errors"] == {"start_time": "invalid_time"}
    result = await hass.config_entries.flow.async_configure(flow_id, {"start_time": "sunset - 0:30"})
    assert result["errors"] == {"base": "time_pair"}
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"start_time": "sunset - 0:30", "end_time": "7:00"}
    )
    assert result["type"] is FlowResultType.MENU

    await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": "night_mode"})
    result = await hass.config_entries.flow.async_configure(flow_id, {"enabled": True, "start_time": "22:00"})
    assert result["errors"] == {"end_time": "required_night_time"}
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"enabled": True, "start_time": "22:00", "end_time": "06:00", "delay": 20, "service_data": {"brightness_pct": 5}}
    )
    assert result["type"] is FlowResultType.MENU

    await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": "advanced"})
    result = await hass.config_entries.flow.async_configure(flow_id, {"ignored_event_sources": ["adapt_(["]})
    assert result["errors"] == {"ignored_event_sources": "invalid_regex"}
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"ignored_event_sources": ["adapt_lgt_.*"], "state_attributes_ignore": ["brightness"], "sensor_states_on": ["occupied"]}
    )
    assert result["type"] is FlowResultType.MENU

    await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": "behaviours"})
    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            "on_enter_idle": "off", "on_exit_idle": "ignore", "on_enter_active": "on", "on_exit_active": "ignore",
            "on_enter_overridden": "ignore", "on_exit_overridden": "ignore", "on_enter_constrained": "off",
            "on_exit_constrained": "ignore", "on_enter_blocked": "ignore", "on_exit_blocked": "ignore",
        },
    )
    assert result["type"] is FlowResultType.MENU

    await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": "blocking"})
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"overrides": ["input_boolean.override"], "disable_block": False, "block_timeout": 300, "grace_period": 3}
    )
    await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": "timer"})
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"delay": 120, "stay_mode": False, "backoff": True, "backoff_factor": 1.5, "backoff_max": 900}
    )
    await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": "service_data"})
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"service_data": {"transition": 2}, "service_data_off": {"transition": 10}}
    )

    result = await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": "finish"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    o = result["options"]
    assert (o["start_time"], o["end_time"]) == ("sunset - 00:30:00", "07:00:00")
    assert o["night_mode"] == {
        "enabled": True, "start_time": "22:00:00", "end_time": "06:00:00", "delay": 20,
        "service_data": {"brightness_pct": 5}, "service_data_off": {},
    }
    assert o["ignored_event_sources"] == ["adapt_lgt_.*"]
    assert o["state_attributes_ignore"] == ["brightness"]
    assert o["sensor_states_on"] == ["occupied"]
    assert o["behaviours"]["on_enter_constrained"] == "off"
    assert (o["overrides"], o["block_timeout"], o["grace_period"]) == (["input_boolean.override"], 300, 3)
    assert (o["delay"], o["backoff"], o["backoff_factor"], o["backoff_max"]) == (120, True, 1.5, 900)
    assert (o["service_data"], o["service_data_off"]) == ({"transition": 2}, {"transition": 10})


async def test_options_flow_edits_and_reloads(hass, freezer, entities):
    entry = await setup_controller(hass, freezer)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert "save" in result["menu_options"]

    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "entities"})
    assert result["step_id"] == "entities"
    # The form is pre-filled with the current values.
    schema_keys = {str(k): k for k in result["data_schema"].schema}
    assert schema_keys["entities"].description == {"suggested_value": [LIGHT]}

    result = await hass.config_entries.options.async_configure(result["flow_id"], {"entities": [LIGHT, LIGHT2]})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["entities"] == [LIGHT, LIGHT2]

    # The controller was reloaded with the new options.
    await advance(hass, freezer, 2)
    await set_state(hass, MOTION, "on")
    assert state(hass, LIGHT) == "on"
    assert state(hass, LIGHT2) == "on"


async def test_options_flow_clearing_optional_fields(hass, freezer, entities):
    entry = await setup_controller(hass, freezer, block_timeout=100, overrides=["input_boolean.override"])
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "blocking"})
    # Cleared fields are omitted by the frontend.
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"disable_block": False})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "save"})
    await hass.async_block_till_done()
    assert entry.options["block_timeout"] is None
    assert entry.options["overrides"] == []


async def test_yaml_import(hass, freezer, entities):
    config = {
        DOMAIN: {
            "hall_motion": {
                "friendly_name": "Hall Motion Light",
                "sensor": MOTION,
                "sensors": [PRESENCE],
                "entity": LIGHT,
                "delay": "45",
                "sensor_type": "Duration",
                "stay_mode": "on",
                "start_time": 79200,  # unquoted 22:00:00 in YAML 1.1
                "end_time": "07:00:00",
                "behaviours": {"on_enter_constrained": False},
                "night_mode": {"start_time": "23:00:00", "end_time": "05:00:00", "service_data": {"brightness": 5}},
                "service_data_on": {"transition": 1},
                "hold_max_seconds": 3600,
                "draw": True,
            },
            "broken": {"sensor": MOTION, "entity": LIGHT, "sensor_type": "sometimes"},
        }
    }
    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.title == "Hall Motion Light"
    assert entry.unique_id == "yaml_hall_motion"
    o = entry.options
    assert o["sensors"] == [MOTION, PRESENCE]
    assert o["entities"] == [LIGHT]
    assert (o["delay"], o["sensor_type"], o["stay_mode"]) == (45, "duration", True)
    assert (o["start_time"], o["end_time"]) == ("22:00:00", "07:00:00")
    assert o["behaviours"]["on_enter_constrained"] == "off"
    assert o["night_mode"]["service_data"] == {"brightness": 5}
    assert o["service_data"] == {"transition": 1}
    assert o["max_hold_time"] == 3600

    # Same entity id as the old YAML controller (friendly name based).
    await advance(hass, freezer, 2)
    assert hass.states.get("entity_controller.hall_motion_light") is not None

    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, "deprecated_yaml") is not None
    assert issues.async_get_issue(DOMAIN, "yaml_import_failed") is not None


async def test_yaml_import_runs_once(hass, entities):
    config = {DOMAIN: {"hall": {"sensor": MOTION, "entity": LIGHT}}}
    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data={"yaml_key": "hall", "title": "hall", "options": {}, "entity_id": "entity_controller.hall"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
