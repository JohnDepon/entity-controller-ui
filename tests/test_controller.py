"""Behaviour of the controller state machine on a real Home Assistant core."""
from homeassistant.core import Context

from .conftest import (
    EC,
    FAN,
    LIGHT,
    LIGHT2,
    MOTION,
    OVERRIDE,
    PRESENCE,
    advance,
    set_state,
    setup_controller,
    state,
)


async def test_event_sensor_turns_off_after_delay(hass, freezer, entities):
    await setup_controller(hass, freezer, delay=60)
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    assert state(hass) == "active_timer"
    assert state(hass, LIGHT) == "on"

    await advance(hass, freezer, 59)
    assert state(hass, LIGHT) == "on"
    await advance(hass, freezer, 2)
    assert state(hass) == "idle"
    assert state(hass, LIGHT) == "off"


async def test_retrigger_restarts_timer(hass, freezer, entities):
    await setup_controller(hass, freezer, delay=60)
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 50)
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 50)
    assert state(hass, LIGHT) == "on"
    await advance(hass, freezer, 11)
    assert state(hass, LIGHT) == "off"


async def test_duration_multiple_sensors_stay_on_while_any_sensor_on(hass, freezer, entities):
    """The reported bug: with several duration sensors the lights turned off
    as soon as ONE sensor went off after the timer expired, although another
    sensor still reported presence."""
    await setup_controller(
        hass, freezer, sensors=[MOTION, PRESENCE], sensor_type="duration", delay=60
    )
    await set_state(hass, MOTION, "on")
    await set_state(hass, PRESENCE, "on")
    assert state(hass) == "active_timer"

    # Timer expires while both sensors are on: wait for the sensors.
    await advance(hass, freezer, 61)
    assert state(hass) == "active_timer"
    assert hass.states.get(EC).attributes["expires_at"] == "pending sensor"

    # Motion sensor clears, presence sensor still on -> must stay on.
    await set_state(hass, MOTION, "off")
    assert state(hass) == "active_timer"
    assert state(hass, LIGHT) == "on"

    # Motion comes and goes again for a while; still on.
    await set_state(hass, MOTION, "on")
    await advance(hass, freezer, 120)
    await set_state(hass, MOTION, "off")
    assert state(hass, LIGHT) == "on"

    # Last sensor clears after the timer expired -> off.
    await set_state(hass, PRESENCE, "off")
    assert state(hass) == "idle"
    assert state(hass, LIGHT) == "off"


async def test_duration_sensor_off_before_timer(hass, freezer, entities):
    await setup_controller(hass, freezer, sensor_type="duration", delay=60)
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    assert state(hass) == "active_timer"
    await advance(hass, freezer, 61)
    assert state(hass) == "idle"
    assert state(hass, LIGHT) == "off"


async def test_duration_sensor_resets_timer_with_multiple_sensors(hass, freezer, entities):
    await setup_controller(
        hass,
        freezer,
        sensors=[MOTION, PRESENCE],
        sensor_type="duration",
        sensor_resets_timer=True,
        delay=60,
    )
    await set_state(hass, MOTION, "on")
    await set_state(hass, PRESENCE, "on")
    await advance(hass, freezer, 61)
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 120)
    assert state(hass, LIGHT) == "on"

    await set_state(hass, PRESENCE, "off")
    # The full delay starts again when the last sensor turns off.
    await advance(hass, freezer, 59)
    assert state(hass, LIGHT) == "on"
    await advance(hass, freezer, 2)
    assert state(hass, LIGHT) == "off"


async def test_hold_sensor_keeps_on_but_never_triggers(hass, freezer, entities):
    await setup_controller(hass, freezer, hold_sensors=[PRESENCE], delay=60)
    await set_state(hass, PRESENCE, "on")
    assert state(hass) == "idle"
    assert state(hass, LIGHT) == "off"

    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    assert state(hass, LIGHT) == "on"
    await advance(hass, freezer, 300)
    assert state(hass) == "active_timer"
    assert state(hass, LIGHT) == "on"

    await set_state(hass, PRESENCE, "off")
    assert state(hass) == "idle"
    assert state(hass, LIGHT) == "off"


async def test_unavailable_duration_sensor_falls_back_to_timer(hass, freezer, entities):
    await setup_controller(hass, freezer, sensor_type="duration", delay=60)
    await set_state(hass, MOTION, "on")
    await advance(hass, freezer, 61)
    assert hass.states.get(EC).attributes["expires_at"] == "pending sensor"

    # Sensor drops off the network: no immediate off, but not stuck forever.
    await set_state(hass, MOTION, "unavailable")
    assert state(hass, LIGHT) == "on"
    await advance(hass, freezer, 61)
    assert state(hass) == "idle"
    assert state(hass, LIGHT) == "off"


async def test_manual_on_blocks_and_manual_off_releases(hass, freezer, entities):
    await setup_controller(hass, freezer)
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": LIGHT}, blocking=True)
    await hass.async_block_till_done()
    await set_state(hass, MOTION, "on")
    assert state(hass) == "blocked"
    await advance(hass, freezer, 600)
    assert state(hass, LIGHT) == "on"

    await hass.services.async_call("input_boolean", "turn_off", {"entity_id": LIGHT}, blocking=True)
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    assert state(hass) == "idle"


async def test_manual_change_while_active_blocks(hass, freezer, entities):
    await setup_controller(hass, freezer)
    await set_state(hass, MOTION, "on")
    assert state(hass) == "active_timer"
    # Someone else changes the light (fresh context): EC steps back.
    hass.states.async_set(LIGHT, "on", {"brightness": 10}, context=Context())
    await hass.async_block_till_done()
    assert state(hass) == "blocked"


async def test_block_timeout(hass, freezer, entities):
    await setup_controller(hass, freezer, block_timeout=120, delay=60)
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": LIGHT}, blocking=True)
    await hass.async_block_till_done()
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    assert state(hass) == "blocked"
    await advance(hass, freezer, 121)
    # Event sensor: EC adopts the light and its timer turns it off.
    assert state(hass) == "active_timer"
    await advance(hass, freezer, 61)
    assert state(hass, LIGHT) == "off"


async def test_disable_block(hass, freezer, entities):
    await setup_controller(hass, freezer, disable_block=True, delay=60)
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": LIGHT}, blocking=True)
    await hass.async_block_till_done()
    await set_state(hass, MOTION, "on")
    assert state(hass) == "active_timer"
    await advance(hass, freezer, 61)
    assert state(hass, LIGHT) == "off"


async def test_override(hass, freezer, entities):
    await setup_controller(hass, freezer, overrides=[OVERRIDE])
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": OVERRIDE}, blocking=True)
    await hass.async_block_till_done()
    assert state(hass) == "overridden"
    await set_state(hass, MOTION, "on")
    assert state(hass, LIGHT) == "off"
    await hass.services.async_call("input_boolean", "turn_off", {"entity_id": OVERRIDE}, blocking=True)
    await hass.async_block_till_done()
    assert state(hass) == "idle"


async def test_override_in_stay_mode(hass, freezer, entities):
    await setup_controller(hass, freezer, overrides=[OVERRIDE], stay_mode=True)
    await set_state(hass, MOTION, "on")
    assert state(hass) == "active_stay_on"
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": OVERRIDE}, blocking=True)
    await hass.async_block_till_done()
    assert state(hass) == "overridden"


async def test_stay_mode_has_no_timer(hass, freezer, entities):
    await setup_controller(hass, freezer, stay_mode=True, delay=60)
    await set_state(hass, MOTION, "on")
    assert state(hass) == "active_stay_on"
    await advance(hass, freezer, 3600)
    assert state(hass) == "active_stay_on"
    assert state(hass, LIGHT) == "on"
    await hass.services.async_call("input_boolean", "turn_off", {"entity_id": LIGHT}, blocking=True)
    await hass.async_block_till_done()
    assert state(hass) == "idle"


async def test_service_data_and_trigger_entities(hass, freezer, entities):
    calls = []

    async def record(call):
        calls.append((call.service, dict(call.data)))

    hass.services.async_register("script", "turn_on", record)
    await setup_controller(
        hass,
        freezer,
        entities=[],
        state_entities=[LIGHT],
        trigger_on_activate=["script.on"],
        trigger_on_deactivate=["script.off"],
        service_data={"variables": {"room": "office"}},
        delay=60,
    )
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    assert calls == [("turn_on", {"entity_id": "script.on", "variables": {"room": "office"}})]
    await advance(hass, freezer, 61)
    assert calls[-1] == ("turn_on", {"entity_id": "script.off"})


async def test_two_controllers_sharing_a_light(hass, freezer, entities):
    """A controller must not ignore changes made by another controller
    (it used to stay blocked forever)."""
    await setup_controller(hass, freezer, title="Test", delay=60)
    await setup_controller(hass, freezer, title="Other", sensors=[PRESENCE], delay=600)
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    assert state(hass, LIGHT) == "on"
    await set_state(hass, PRESENCE, "on")
    await set_state(hass, PRESENCE, "off")
    assert state(hass, "entity_controller.other") == "blocked"

    await advance(hass, freezer, 61)  # first controller turns the light off
    assert state(hass, LIGHT) == "off"
    assert state(hass, "entity_controller.other") == "idle"


async def test_controlled_entity_unavailable_is_not_manual_control(hass, freezer, entities):
    await setup_controller(hass, freezer, delay=60)
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    hass.states.async_set(LIGHT, "unavailable", context=Context())
    await hass.async_block_till_done()
    assert state(hass) == "active_timer"
    hass.states.async_set(LIGHT, "on", context=Context())
    await hass.async_block_till_done()
    assert state(hass) == "active_timer"
    await advance(hass, freezer, 61)
    assert state(hass) == "idle"


async def test_ignored_attributes(hass, freezer, entities):
    await setup_controller(hass, freezer, state_attributes_ignore=["brightness"])
    await set_state(hass, MOTION, "on")
    attrs = dict(hass.states.get(LIGHT).attributes)
    hass.states.async_set(LIGHT, "on", {**attrs, "brightness": 50}, context=Context())
    await hass.async_block_till_done()
    hass.states.async_set(LIGHT, "on", {**attrs, "brightness": 60}, context=Context())
    await hass.async_block_till_done()
    assert state(hass) == "active_timer"


async def test_grace_period(hass, freezer, entities):
    await setup_controller(hass, freezer, grace_period=5)
    await set_state(hass, MOTION, "on")
    # A late state update without EC's context, within the grace period.
    hass.states.async_set(LIGHT, "on", {"brightness": 99}, context=Context())
    await hass.async_block_till_done()
    assert state(hass) == "active_timer"


async def test_backoff(hass, freezer, entities):
    await setup_controller(hass, freezer, backoff=True, backoff_factor=2, backoff_max=200, delay=60)
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    await set_state(hass, MOTION, "on")  # 120 s
    await set_state(hass, MOTION, "off")
    await set_state(hass, MOTION, "on")  # 240 s, capped to 200 s
    await set_state(hass, MOTION, "off")
    assert hass.states.get(EC).attributes["delay"] == "200s"
    await advance(hass, freezer, 199)
    assert state(hass, LIGHT) == "on"
    await advance(hass, freezer, 2)
    assert state(hass, LIGHT) == "off"


async def test_custom_state_strings(hass, freezer, entities):
    await setup_controller(
        hass,
        freezer,
        sensors=["sensor.room"],
        sensor_states_on=["occupied"],
        sensor_states_off=["empty"],
        sensor_type="duration",
        delay=10,
    )
    await set_state(hass, "sensor.room", "occupied")
    assert state(hass, LIGHT) == "on"
    await advance(hass, freezer, 11)
    assert state(hass, LIGHT) == "on"
    await set_state(hass, "sensor.room", "empty")
    assert state(hass, LIGHT) == "off"


async def test_behaviours(hass, freezer, entities):
    await setup_controller(
        hass,
        freezer,
        behaviours={"on_enter_idle": "ignore", "on_enter_active": "on"},
        delay=10,
    )
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 11)
    assert state(hass) == "idle"
    assert state(hass, LIGHT) == "on"  # on_enter_idle: ignore


async def test_services(hass, freezer, entities):
    await setup_controller(hass, freezer, delay=60, block_timeout=None)
    await hass.services.async_call("entity_controller", "activate", {"entity_id": EC}, blocking=True)
    await hass.async_block_till_done()
    assert state(hass) == "active_timer"
    assert state(hass, LIGHT) == "on"

    await hass.services.async_call("entity_controller", "enable_block", {"entity_id": EC}, blocking=True)
    await hass.async_block_till_done()
    assert state(hass) == "blocked"
    await hass.services.async_call("entity_controller", "clear_block", {"entity_id": EC}, blocking=True)
    await hass.async_block_till_done()
    assert state(hass) == "active_timer"

    await hass.services.async_call("entity_controller", "enable_stay_mode", {"entity_id": EC}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(EC).attributes["stay_mode"] is True
    await hass.services.async_call("entity_controller", "disable_stay_mode", {"entity_id": EC}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(EC).attributes["stay_mode"] is False

    # Not valid in stay/overridden states: logged, never raised.
    await hass.services.async_call("entity_controller", "set_night_mode", {"entity_id": EC}, blocking=True)
    await hass.async_block_till_done()


async def test_night_mode_parameters(hass, freezer, entities):
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-06-01 23:00:00+00:00")
    await setup_controller(
        hass,
        freezer,
        delay=300,
        service_data={"brightness": 255},
        night_mode={
            "enabled": True,
            "start_time": "22:00:00",
            "end_time": "06:00:00",
            "delay": 30,
            "service_data": {},
            "service_data_off": {},
        },
    )
    await set_state(hass, MOTION, "on")
    attrs = hass.states.get(EC).attributes
    assert attrs["mode"] == "night"
    assert attrs["delay"] == "30s"
    # Night service data falls back to the day service data when empty.
    assert attrs["service_data"] == {"brightness": 255}


async def test_max_hold_time_releases_stuck_hold_sensor(hass, freezer, entities, caplog):
    await setup_controller(hass, freezer, hold_sensors=[PRESENCE], max_hold_time=600, delay=60)
    await set_state(hass, PRESENCE, "on")  # gets stuck from here on
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 61)
    assert state(hass) == "active_timer"  # held: on for less than 600 s
    assert hass.states.get(EC).attributes["expires_at"] == "pending sensor"

    await advance(hass, freezer, 500)
    assert state(hass, LIGHT) == "on"
    await advance(hass, freezer, 45)  # presence has now been on for > 600 s
    assert state(hass) == "idle"
    assert state(hass, LIGHT) == "off"
    assert caplog.text.count("longer than the maximum hold time") == 1

    # A stuck sensor does not prevent new triggers.
    await set_state(hass, MOTION, "on")
    assert state(hass, LIGHT) == "on"
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 61)
    assert state(hass, LIGHT) == "off"


async def test_max_hold_time_releases_stuck_duration_trigger_sensor(hass, freezer, entities):
    """mmWave as a duration trigger sensor (as imported from YAML) stuck on."""
    await setup_controller(
        hass, freezer, sensors=[MOTION, PRESENCE], sensor_type="duration", max_hold_time=600, delay=60
    )
    await set_state(hass, MOTION, "on")
    await set_state(hass, PRESENCE, "on")
    await advance(hass, freezer, 10)
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 580)
    assert state(hass, LIGHT) == "on"
    await advance(hass, freezer, 15)
    assert state(hass) == "idle"
    assert state(hass, LIGHT) == "off"


async def test_max_hold_time_with_sensor_resets_timer(hass, freezer, entities):
    await setup_controller(
        hass,
        freezer,
        hold_sensors=[PRESENCE],
        max_hold_time=600,
        sensor_resets_timer=True,
        delay=60,
    )
    await set_state(hass, PRESENCE, "on")
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 61)
    assert hass.states.get(EC).attributes["expires_at"] == "pending sensor"
    await advance(hass, freezer, 545)
    # Limit reached: the full delay runs once more.
    assert state(hass) == "active_timer"
    await advance(hass, freezer, 61)
    assert state(hass) == "idle"


async def test_without_max_hold_time_sensor_holds_indefinitely(hass, freezer, entities):
    await setup_controller(hass, freezer, hold_sensors=[PRESENCE], delay=60)
    await set_state(hass, PRESENCE, "on")
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 24 * 3600)
    assert state(hass, LIGHT) == "on"


async def test_service_data_templates(hass, freezer, entities):
    from pytest_homeassistant_custom_component.common import async_mock_service

    calls = async_mock_service(hass, "light", "turn_on")
    hass.states.async_set("light.bath", "off")
    hass.states.async_set("input_boolean.dnd", "on")
    await setup_controller(
        hass,
        freezer,
        entities=["light.bath"],
        delay=60,
        service_data={
            "brightness_pct": "{{ 50 if is_state('input_boolean.dnd', 'on') else 100 }}",
            "transition": 2,
            "broken": "{{ states( }}",
        },
    )
    await set_state(hass, MOTION, "on")
    await set_state(hass, MOTION, "off")
    # Rendered at call time; a broken template only drops its own key.
    assert calls[-1].data == {"entity_id": "light.bath", "brightness_pct": 50, "transition": 2}

    await advance(hass, freezer, 61)
    hass.states.async_set("input_boolean.dnd", "off")
    await set_state(hass, MOTION, "on")
    assert calls[-1].data["brightness_pct"] == 100


DELAYED = {"sensor_type": "duration", "delay": 60, "delayed_entities": [FAN], "delayed_after": 120, "delayed_min_on": 300}


async def test_delayed_fan_runs_min_time_after_leaving(hass, freezer, entities):
    await setup_controller(hass, freezer, **DELAYED)
    await set_state(hass, MOTION, "on")
    await advance(hass, freezer, 119)
    assert state(hass, FAN) == "off"
    await advance(hass, freezer, 2)  # stayed longer than 120 s
    assert state(hass, FAN) == "on"

    await set_state(hass, MOTION, "off")  # leave: light off, fan keeps running
    assert state(hass, LIGHT) == "off"
    assert state(hass, FAN) == "on"
    await advance(hass, freezer, 298)
    assert state(hass, FAN) == "on"
    await advance(hass, freezer, 3)  # 300 s after it was turned on
    assert state(hass, FAN) == "off"


async def test_delayed_fan_not_started_when_leaving_early(hass, freezer, entities):
    await setup_controller(hass, freezer, **DELAYED)
    await set_state(hass, MOTION, "on")
    await advance(hass, freezer, 30)
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 31)
    assert state(hass, LIGHT) == "off"
    await advance(hass, freezer, 300)
    assert state(hass, FAN) == "off"


async def test_delayed_fan_stays_on_while_still_there(hass, freezer, entities):
    await setup_controller(hass, freezer, **DELAYED)
    await set_state(hass, MOTION, "on")
    await advance(hass, freezer, 121)
    await advance(hass, freezer, 480)  # well past the 300 s minimum, still there
    assert state(hass, FAN) == "on"
    await set_state(hass, MOTION, "off")  # nobody there any more
    assert state(hass, LIGHT) == "off"
    assert state(hass, FAN) == "off"


async def test_delayed_fan_back_in_the_room_during_min_time(hass, freezer, entities):
    await setup_controller(hass, freezer, **DELAYED)
    await set_state(hass, MOTION, "on")
    await advance(hass, freezer, 121)
    await set_state(hass, MOTION, "off")  # leave, fan keeps running
    await advance(hass, freezer, 80)
    await set_state(hass, MOTION, "on")  # back before the minimum ends
    await advance(hass, freezer, 300)  # minimum over while there
    assert state(hass, FAN) == "on"
    await set_state(hass, MOTION, "off")
    assert state(hass, FAN) == "off"


async def test_delayed_fan_already_on_is_left_alone(hass, freezer, entities):
    await setup_controller(hass, freezer, **DELAYED)
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": FAN}, blocking=True)
    await set_state(hass, MOTION, "on")
    await advance(hass, freezer, 121)
    await set_state(hass, MOTION, "off")
    await advance(hass, freezer, 600)
    assert state(hass, FAN) == "on"
