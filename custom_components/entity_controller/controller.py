"""
This file is part of Entity Controller.
Modified in October 2026 for the UI configuration fork (see CHANGELOG.md).

Entity Controller is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Entity Controller is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Entity Controller.  If not, see <https://www.gnu.org/licenses/>.

"""
"""The Entity Controller finite state machine.

This is the original Entity Controller model, reworked so that everything
(timers, state machine transitions, service calls) runs on the Home Assistant
event loop. The original implementation drove the state machine from
``threading.Timer`` threads concurrently with the event loop, which caused
races between "motion detected" and "timer expired".
"""

import copy
import hashlib
import logging
import pprint
import re
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from typing import Any, Callable

from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    SUN_EVENT_SUNRISE,
    SUN_EVENT_SUNSET,
)
from homeassistant.core import Context, CoreState, HomeAssistant, State, callback
from homeassistant.exceptions import ServiceNotFound, TemplateError
from homeassistant.helpers import event, template
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt, slugify
import homeassistant.util.uuid as uuid_util
from transitions.core import MachineError
from transitions.extensions import HierarchicalMachine as Machine

from .const import (
    CONF_BACKOFF,
    CONF_BACKOFF_FACTOR,
    CONF_BACKOFF_MAX,
    CONF_BEHAVIOURS,
    CONF_BLOCK_TIMEOUT,
    CONF_CONTROL_ENTITIES,
    CONF_CONTROL_STATES_OFF,
    CONF_CONTROL_STATES_ON,
    CONF_DAY_LENGTH,
    CONF_DELAY,
    CONF_DELAYED_AFTER,
    CONF_DELAYED_ENTITIES,
    CONF_DELAYED_MIN_ON,
    CONF_DISABLE_BLOCK,
    CONF_ENABLED,
    CONF_END_TIME,
    CONF_GRACE_PERIOD,
    CONF_HOLD_SENSORS,
    CONF_IGNORED_EVENT_SOURCES,
    CONF_MAX_HOLD_TIME,
    CONF_NIGHT_MODE,
    CONF_ON_ENTER_ACTIVE,
    CONF_ON_ENTER_BLOCKED,
    CONF_ON_ENTER_CONSTRAINED,
    CONF_ON_ENTER_IDLE,
    CONF_ON_ENTER_OVERRIDDEN,
    CONF_ON_EXIT_ACTIVE,
    CONF_ON_EXIT_BLOCKED,
    CONF_ON_EXIT_CONSTRAINED,
    CONF_ON_EXIT_IDLE,
    CONF_ON_EXIT_OVERRIDDEN,
    CONF_OVERRIDE_STATES_OFF,
    CONF_OVERRIDE_STATES_ON,
    CONF_OVERRIDES,
    CONF_SENSOR_RESETS_TIMER,
    CONF_SENSOR_STATES_OFF,
    CONF_SENSOR_STATES_ON,
    CONF_SENSOR_TYPE,
    CONF_SENSORS,
    CONF_SERVICE_DATA,
    CONF_SERVICE_DATA_OFF,
    CONF_START_TIME,
    CONF_STATE_ATTRIBUTES_IGNORE,
    CONF_STATE_ENTITIES,
    CONF_STATE_STATES_OFF,
    CONF_STATE_STATES_ON,
    CONF_STATE_STRINGS_OFF,
    CONF_STATE_STRINGS_ON,
    CONF_STAY_MODE,
    CONF_TRANSITION_BEHAVIOUR_IGNORE,
    CONF_TRANSITION_BEHAVIOUR_OFF,
    CONF_TRANSITION_BEHAVIOUR_ON,
    CONF_TRIGGER_ON_ACTIVATE,
    CONF_TRIGGER_ON_DEACTIVATE,
    CONTEXT_ID_CHARACTER_LIMIT,
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_BACKOFF_MAX,
    DEFAULT_BEHAVIOURS,
    DEFAULT_DELAY,
    DEFAULT_STATES_OFF,
    DEFAULT_STATES_ON,
    DOMAIN,
    DOMAIN_SHORT,
    MODE_DAY,
    MODE_NIGHT,
    RELOAD_DELAY,
    SENSOR_TYPE_DURATION,
    SENSOR_TYPE_EVENT,
    STARTUP_DELAY,
    STATES,
)

_LOGGER = logging.getLogger(__package__)

# States that mean "this entity currently cannot tell us anything".
NEUTRAL_STATES = (STATE_UNAVAILABLE, STATE_UNKNOWN)


def build_machine() -> Machine:
    """Create the state machine shared by all Entity Controller models."""
    machine = Machine(
        model=None,
        states=STATES,
        initial="pending",
        finalize_event="finalize",
        auto_transitions=False,
    )
    machine.add_transition(trigger="start_monitoring", source="pending", dest="idle")

    machine.add_transition(trigger="constrain", source="*", dest="constrained")
    machine.add_transition(
        trigger="override",
        # active_stay_on was missing: overrides had no effect in stay mode.
        source=["pending", "idle", "active_timer", "active_stay_on", "blocked"],
        dest="overridden",
    )

    machine.add_transition(trigger="activate", source=["idle", "blocked"], dest="active")
    machine.add_transition(
        trigger="activate", source="active_timer", dest=None, after="_reset_timer"
    )

    # Idle
    machine.add_transition(
        trigger="sensor_on", source="idle", dest="active", conditions=["is_state_entities_off"]
    )
    machine.add_transition(
        trigger="sensor_on",
        source="idle",
        dest="active",
        conditions=["is_state_entities_on"],
        unless="is_block_enabled",
    )
    machine.add_transition(
        trigger="sensor_on",
        source="idle",
        dest="blocked",
        conditions=["is_state_entities_on", "is_block_enabled"],
    )
    machine.add_transition(
        trigger="enable", source="idle", dest=None, conditions=["is_state_entities_off"]
    )
    # start_time can fire while already idle (e.g. HA restarted inside the
    # window). Without this, blocked() raised MachineError from a time callback.
    machine.add_transition(
        trigger="blocked", source="idle", dest="blocked", conditions=["is_block_enabled"]
    )

    # Blocked
    machine.add_transition(
        trigger="enable", source="blocked", dest="idle", conditions=["is_state_entities_off"]
    )
    # Safety net (floris-b fork): if the "off" event of the state entities was
    # missed, a new trigger must not leave EC stuck in blocked.
    machine.add_transition(
        trigger="sensor_on", source="blocked", dest="active", conditions=["is_state_entities_off"]
    )
    machine.add_transition(
        trigger="sensor_on", source="blocked", dest="blocked", conditions=["is_block_enabled"]
    )  # re-entering self-transition (on_enter callback executed.)

    # Overridden. The first rule keeps EC overridden while any override entity
    # is still on (pluskal fork: enable() used to clear an active override).
    machine.add_transition(
        trigger="enable", source="overridden", dest=None, conditions=["is_override_state_on"]
    )
    machine.add_transition(
        trigger="enable", source="overridden", dest="idle", conditions=["is_state_entities_off"]
    )
    # If a device leaving overridden is on, we do not necessarily want to shut
    # it off immediately. We simply want EC to stop controlling it. To do that,
    # we move it to active, to simulate an EC trigger, and see if it exits on
    # its own. A duration sensor that is off now will never expire on its own,
    # so in that case we assume the target is 'idle'.
    machine.add_transition(
        trigger="enable",
        source="overridden",
        dest="active",
        conditions=["is_state_entities_on", "is_event_sensor"],
    )
    machine.add_transition(
        trigger="enable",
        source="overridden",
        dest="active",
        conditions=["is_state_entities_on", "is_sensor_on"],
    )
    machine.add_transition(
        trigger="enable",
        source="overridden",
        dest="idle",
        conditions=["is_state_entities_on", "is_duration_sensor", "is_sensor_off"],
    )

    machine.add_transition(trigger="enter", source="active", dest="active_timer", unless="will_stay_on")
    machine.add_transition(
        trigger="enter", source="active", dest="active_stay_on", conditions="will_stay_on"
    )

    # Active Timer
    machine.add_transition(trigger="sensor_on", source="active_timer", dest=None, after="_reset_timer")
    # A sensor released (went off) after the timer expired. FIX: the original
    # only checked the timer, so with several sensors the first sensor to go off
    # switched the lights off although other sensors still reported presence.
    machine.add_transition(
        trigger="sensor_off_duration",
        source="active_timer",
        dest="idle",
        conditions=["is_timer_expired", "is_released"],
    )
    # The following two transitions must be kept separate because they have
    # special conditional logic that cannot be combined.
    machine.add_transition(
        trigger="timer_expires", source="active_timer", dest="idle", conditions=["is_event_sensor"]
    )
    machine.add_transition(
        trigger="timer_expires",
        source="active_timer",
        dest="idle",
        conditions=["is_duration_sensor", "is_sensor_off"],
    )

    machine.add_transition(
        trigger="block_timer_expires",
        source="blocked",
        dest="active",
        conditions=["is_state_entities_on", "is_event_sensor"],
    )
    machine.add_transition(
        trigger="block_timer_expires",
        source="blocked",
        dest="active",
        conditions=["is_state_entities_on", "is_sensor_on"],
    )
    machine.add_transition(
        trigger="block_timer_expires",
        source="blocked",
        dest="idle",
        conditions=["is_state_entities_on", "is_duration_sensor", "is_sensor_off"],
    )
    # Catch-all (pluskal fork): without it EC could stay blocked forever after
    # the block timeout when none of the rules above matched.
    machine.add_transition(trigger="block_timer_expires", source="blocked", dest="idle")

    machine.add_transition(
        trigger="control", source="active_timer", dest="idle", conditions=["is_state_entities_off"]
    )
    machine.add_transition(
        trigger="control",
        source="active_timer",
        dest="blocked",
        conditions=["is_state_entities_on", "is_block_enabled"],
    )
    # When block is disabled, "control" will reset the active timer
    machine.add_transition(
        trigger="control",
        source="active_timer",
        dest=None,
        after="_reset_timer",
        conditions=["is_state_entities_on"],
        unless="is_block_enabled",
    )
    # Manually enable blocked state
    machine.add_transition(
        trigger="block_enable",
        source="active_timer",
        dest="blocked",
        conditions=["is_state_entities_on", "is_block_enabled"],
    )

    machine.add_transition(
        trigger="enable", source="active_stay_on", dest="idle", conditions=["is_state_entities_off"]
    )
    # Constrained
    machine.add_transition(
        trigger="enable", source="constrained", dest="idle", conditions=["is_override_state_off"]
    )
    machine.add_transition(
        trigger="enable", source="constrained", dest="overridden", conditions=["is_override_state_on"]
    )
    # Enter blocked state when component is enabled and entity is on
    machine.add_transition(
        trigger="blocked", source="constrained", dest="blocked", conditions=["is_block_enabled"]
    )
    return machine


class Model:
    """Represents the transitions state machine model of one controller."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        instance_id: str,
        options: dict[str, Any],
        machine: Machine,
        entity,
    ) -> None:
        self.hass = hass
        self.entity = entity  # backwards reference to entity containing this model
        self.machine = machine
        self.name = name
        self.config = copy.deepcopy(options)
        # Renamed to the entity object id once known (see EntityController).
        self.log = logging.getLogger(f"{__package__}.{slugify(name)}")

        self.stateEntities: list[str] = []
        self.controlEntities: list[str] = []
        self.sensorEntities: list[str] = []
        self.holdSensorEntities: list[str] = []
        self.overrideEntities: list[str] = []
        self.triggerOnDeactivate: list[str] = []
        self.triggerOnActivate: list[str] = []
        # Delayed entities (e.g. a bathroom fan), see _delayed_start.
        self.delayedEntities: list[str] = []
        self.delayed_after = 0
        self.delayed_min_on = 0
        self._delayed_handle: Callable[[], None] | None = None
        self._delayed_running: list[str] = []
        self._delayed_min_done = False
        self._delayed_min_until: datetime | None = None
        # Saved delayed entity state (see delayed_restore_data).
        self.restored_extra: dict[str, Any] | None = None
        # Attributes of the entity before the restart/reload.
        self.restored_attributes: dict[str, Any] = {}
        self.timer_handle: Callable[[], None] | None = None
        self.block_timer_handle: Callable[[], None] | None = None
        self.sensor_type = SENSOR_TYPE_EVENT
        self.night_mode: dict[str, Any] | None = None
        self.state_attributes_ignore: list[str] = []
        self.ignored_event_sources: list[str] = []
        self.backoff = False
        self.backoff_count = 0
        self.backoff_factor = DEFAULT_BACKOFF_FACTOR
        self.backoff_max = DEFAULT_BACKOFF_MAX
        self.previous_delay = DEFAULT_DELAY
        self.light_params_day: dict[str, Any] = {}
        self.light_params_night: dict[str, Any] = {}
        self.lightParams: dict[str, Any] = {}
        self.stay = bool(self.config.get(CONF_STAY_MODE, False))
        self.disable_block = False
        self.block_timeout: int | None = None
        self.grace_period: int | None = None
        self.ignore_state_changes_until = dt.utcnow()
        self.transition_behaviours: dict[str, str] = dict(DEFAULT_BEHAVIOURS)
        self.homeassistant_turn_on_domains = ["group"]
        self.debug_day_length = self.config.get(CONF_DAY_LENGTH)
        self._start_time_private: str | None = None
        self._end_time_private: str | None = None
        self.context: Context | None = None
        self.context_id: str | None = None
        # Unique per controller, short enough to fit the context id length.
        self._context_prefix = (
            f"{DOMAIN_SHORT}_{hashlib.sha1(instance_id.encode('UTF-8')).hexdigest()[:6]}_"
        )
        self._unsubs: list[Callable[[], None]] = []
        self._start_unsub: Callable[[], None] | None = None
        self._end_unsub: Callable[[], None] | None = None
        self._startup_handle: Callable[[], None] | None = None
        self._boot = False
        self._suppress_behaviours = False
        self._warned_missing: set[str] = set()
        # Maximum hold time (seconds) and the re-check scheduled for it.
        self.max_hold_time: int | None = None
        self._hold_check_handle: Callable[[], None] | None = None
        self._warned_held_too_long: set[tuple[str, datetime]] = set()
        self._running = False
        # Last known state of the controller entity (RestoreEntity), used to
        # resume after a restart or reload.
        self.restored_state: str | None = None

        self.CONTROL_ON_STATE: list[str] = []
        self.CONTROL_OFF_STATE: list[str] = []
        self.SENSOR_ON_STATE: list[str] = []
        self.SENSOR_OFF_STATE: list[str] = []
        self.OVERRIDE_ON_STATE: list[str] = []
        self.OVERRIDE_OFF_STATE: list[str] = []
        self.STATE_ON_STATE: list[str] = []
        self.STATE_OFF_STATE: list[str] = []

        self.log.debug("Initialising EntityController entity with this configuration: ")
        self.log.debug(pprint.pformat(self.config))

        machine.add_model(self)  # machine generated methods are used below.

    # =====================================================
    #    L I F E C Y C L E
    # =====================================================

    @callback
    def async_start(self) -> None:
        """Start monitoring once entity states are expected to be settled."""
        if self.hass.state is CoreState.running:
            delay = RELOAD_DELAY
            self._boot = False
        else:
            # Home Assistant is booting; give integrations time to settle.
            delay = STARTUP_DELAY
            self._boot = True
        self._startup_handle = event.async_call_later(
            self.hass, delay, self.startup_delay_callback
        )

    @callback
    def async_shutdown(self) -> None:
        """Release timers and listeners. The model must not be used afterwards."""
        self._running = False
        if self._startup_handle:
            self._startup_handle()
            self._startup_handle = None
        self._cancel_timer()
        self._cancel_block_timer()
        self._cancel_hold_check()
        self._cancel_delayed()
        self._cancel_time_callbacks()
        while self._unsubs:
            self._unsubs.pop()()
        try:
            self.machine.remove_model(self)
        except ValueError:
            pass

    @callback
    def startup_delay_callback(self, _now=None) -> None:
        self._startup_handle = None
        self._running = True
        config = self.config
        self.config_static_strings(config)
        self.config_control_entities(config)
        # must come after config_control_entities (uses control entities if not set)
        self.config_state_entities(config)
        self.config_sensor_entities(config)
        self.config_override_entities(config)
        self.config_transition_behaviours(config)
        self.config_off_entities(config)
        self.config_on_entities(config)
        self.config_normal_mode(config)
        # must come after normal_mode (uses normal mode parameters if not set)
        self.config_night_mode(config)
        self.config_state_attributes_ignore(config)
        self.config_other(config)
        self.prepare_service_data()
        self.update(
            sensor_entities=self.sensorEntities,
            control_entities=self.controlEntities,
            state_entities=self.stateEntities,
            stay_mode=self.stay,
        )
        if self.holdSensorEntities:
            self.update(hold_sensor_entities=self.holdSensorEntities)
        if self.overrideEntities:
            self.update(override_entities=self.overrideEntities)
        if self.delayedEntities:
            self.update(delayed_entities=self.delayedEntities)
            self._delayed_status("off")
        # Before the initial transition, so resuming 'active' does not start
        # the delayed entities again.
        self._delayed_restore()
        self._initial_transition()
        # Keep showing the real last trigger, not the restart/reload.
        for key in ("last_triggered_by", "last_triggered_at"):
            if key in self.restored_attributes:
                self.update(**{key: self.restored_attributes[key]})
        self.config_times(config)

    def _initial_transition(self) -> None:
        """Move out of 'pending', resuming the previous state where sensible."""
        restored = self.restored_state
        self.log.debug("Initial transition, restored state: %s", restored)
        if self.overrideEntities and self.is_override_state_on():
            self.update(overridden_by=self._override_entity_state())
            self.override()
            self.update(overridden_at=str(dt.now()))
            return

        if restored in ("active_timer", "active_stay_on") and self.is_state_entities_on():
            # EC was controlling the entities before the restart/reload and they
            # are still on: resume control (fresh timer) instead of forgetting
            # them, without sending any service call.
            self.log.info("Resuming '%s' after restart/reload", restored)
            with self._quietly():
                self.start_monitoring()
                self.activate()
            self.update(notes="Resumed after restart/reload")
            return

        if restored == "blocked" and self.is_state_entities_on() and self.is_block_enabled():
            # Manually controlled before the restart: stay hands-off. Passing
            # through idle must not switch the entities off (WimImmelman fork).
            self.log.info("Resuming 'blocked' after restart/reload")
            with self._quietly():
                self.start_monitoring()
                self.blocked()
            return

        if self._boot:
            # Original behaviour on Home Assistant start (on_enter_idle runs).
            self.start_monitoring()
        else:
            # A reload (e.g. after editing the options) must not switch loads.
            with self._quietly():
                self.start_monitoring()

    @contextmanager
    def _quietly(self):
        """Run transitions without executing transition behaviours."""
        previous = self._suppress_behaviours
        self._suppress_behaviours = True
        try:
            yield
        finally:
            self._suppress_behaviours = previous

    def _safe_trigger(self, trigger: str, *args) -> bool:
        """Fire a trigger, logging instead of raising when it is not valid now."""
        try:
            return getattr(self, trigger)(*args)
        except MachineError as err:
            self.log.debug("Ignoring trigger '%s' in state '%s': %s", trigger, self.state, err)
            return False

    def update(self, wait=False, **kwargs):
        """Called from different methods to report a state attribute change"""
        for k, v in kwargs.items():
            if v is not None:
                self.entity.set_attr(k, v)

        if wait is False:
            self.entity.do_update()

    def finalize(self):
        self.entity.do_update()

    # =====================================================
    # S T A T E   C H A N G E   C A L L B A C K S
    # =====================================================

    @callback
    def sensor_state_change(self, evt):
        """State change callback for sensor entities"""
        entity = evt.data["entity_id"]
        old = evt.data["old_state"]
        new = evt.data["new_state"]
        if new is None:
            # Entity removed (e.g. platform reload) - nothing to evaluate.
            self.log.debug("sensor_state_change :: %s was removed", entity)
            return
        self.log.debug(
            "sensor_state_change :: %s changed to %s (EC state: %s)", entity, new.state, self.state
        )

        if old is not None and new.state == old.state:
            self.log.debug("sensor_state_change :: Ignore attribute only change")
            return

        if self.matches(new.state, self.SENSOR_ON_STATE):
            if self.is_idle() or self.is_active_timer() or self.is_blocked():
                self.set_context(new.context)
                self.update(last_triggered_by=entity)
                self.sensor_on()
            return

        # We only care about sensor off state changes when the sensor is a
        # duration sensor (they hold the controller active while they are on).
        if self.is_duration_sensor() and (
            self.matches(new.state, self.SENSOR_OFF_STATE) or new.state in NEUTRAL_STATES
        ):
            self._sensor_released(entity, new)

    @callback
    def hold_sensor_state_change(self, evt):
        """State change callback for hold sensors.

        Hold sensors (typically presence/mmWave sensors) keep the controller
        active while they are on, but never activate it on their own.
        """
        entity = evt.data["entity_id"]
        old = evt.data["old_state"]
        new = evt.data["new_state"]
        if new is None or (old is not None and old.state == new.state):
            return
        self.log.debug(
            "hold_sensor_state_change :: %s changed to %s (EC state: %s)",
            entity,
            new.state,
            self.state,
        )
        if self.matches(new.state, self.SENSOR_ON_STATE):
            if self.is_active_timer():
                # Keep-alive: restart the timer, but never switch on from idle.
                self.set_context(new.context)
                self.update(last_triggered_by=entity)
                self.sensor_on()
            return
        if self.matches(new.state, self.SENSOR_OFF_STATE) or new.state in NEUTRAL_STATES:
            self._sensor_released(entity, new)

    def _sensor_released(self, entity: str, new: State) -> None:
        """A sensor stopped reporting presence while EC is active."""
        if not self.is_active_timer():
            return
        if not self.is_released():
            # FIX for multiple sensors: another sensor still reports presence,
            # the lights must stay on.
            self.log.debug(
                "sensor_state_change :: %s is %s, but %s still holds the controller",
                entity,
                new.state,
                self._holding_sensor(),
            )
            return

        self.set_context(new.context)
        self.update(last_triggered_by=entity, sensor_turned_off_at=dt.now())

        if new.state in NEUTRAL_STATES:
            # The sensor became unavailable. Do not switch off immediately (it
            # may be a short connection drop), but make sure the controller
            # does not stay active forever if the timer already expired.
            if self.is_timer_expired():
                self.update(notes=f"{entity} became {new.state}. Timer restarted.")
                self._reset_timer()
            return

        self._release()

    def _release(self, reason: str = "The sensor turned off") -> None:
        """No sensor holds the controller any more."""
        if self.config.get(CONF_SENSOR_RESETS_TIMER):
            # If configured, reset timer when the (last) sensor goes off
            self.log.debug("sensor_state_change :: CONF_SENSOR_RESETS_TIMER")
            self.update(notes=f"{reason} and reset the timeout. Timer started.")
            self._reset_timer()
        else:
            # Goes idle if the timer has already expired.
            self.sensor_off_duration()

    @callback
    def override_state_change(self, evt):
        """State change callback for override entities"""
        entity = evt.data["entity_id"]
        old = evt.data["old_state"]
        new = evt.data["new_state"]
        if new is None:
            self.log.debug("override_state_change :: %s was removed", entity)
            return
        self.log.debug(
            "override_state_change :: Override state change entity=%s, old=%s, new=%s",
            entity,
            old.state if old else None,
            new.state,
        )
        if self.matches(new.state, self.OVERRIDE_ON_STATE) and (
            self.is_idle() or self.is_active_timer() or self.is_active_stay_on() or self.is_blocked()
        ):
            self.set_context(new.context)
            self.update(overridden_by=entity)
            self.override()
            self.update(overridden_at=str(dt.now()))
        if (
            self.matches(new.state, self.OVERRIDE_OFF_STATE)
            and self.is_override_state_off()
            and self.is_overridden()
        ):
            self.set_context(new.context)
            self.enable()

    @callback
    def state_entity_state_change(self, evt):
        """State change callback for state entities.

        This can be called with either a state change or an attribute change.
        """
        entity = evt.data["entity_id"]
        old = evt.data["old_state"]
        new = evt.data["new_state"]
        if new is None:
            self.log.debug("state_entity_state_change :: %s was removed", entity)
            return
        self.log.debug(
            "state_entity_state_change :: [ Entity: %s, Context: %s ]\n\tOld state: %s\n\tNew State: %s",
            entity,
            new.context,
            old,
            new,
        )

        # A lost connection is not a state of the light (pluskal fork). Treating
        # it as "switched off" made EC go idle and fire a turn_off the device
        # never received.
        if new.state in NEUTRAL_STATES:
            self.log.debug(
                "state_entity_state_change :: %s became %s - ignoring", entity, new.state
            )
            return
        came_back = old is not None and old.state in NEUTRAL_STATES
        if came_back:
            # The entity came back after a connection loss. That is not manual
            # control, so it must never push EC into blocked.
            self.log.debug(
                "state_entity_state_change :: %s came back as '%s'", entity, new.state
            )
            if self.is_active_timer() and self.is_state_entities_on():
                return
        else:
            if self.is_ignored_context(new.context):
                self.log.debug(
                    "state_entity_state_change :: Ignoring this state change because it came from %s",
                    new.context.id,
                )
                return
            if self.is_within_grace_period():
                self.log.debug(
                    "state_entity_state_change :: Ignoring this state change because we are within the grace period (until %s)",
                    self.ignore_state_changes_until,
                )
                return

        # If the state changed, we definitely want to handle the transition. If
        # only attributes changed, we check if the new attributes are
        # significant (i.e., not being ignored).
        if old is not None and old.state == new.state:
            old_temp = {
                key: value
                for key, value in old.attributes.items()
                if key not in self.state_attributes_ignore
            }
            new_temp = {
                key: value
                for key, value in new.attributes.items()
                if key not in self.state_attributes_ignore
            }
            if old_temp == new_temp:
                self.log.debug(
                    "state_entity_state_change :: insignificant attribute change - Ignore the state change altogether"
                )
                return
            self.log.debug(
                "state_entity_state_change :: A significant attribute changed and will be handled"
            )

        self.set_context(new.context)
        if self.is_active_timer():
            self.log.debug(
                "state_entity_state_change :: We are in active timer and the state of observed state entities changed."
            )
            self.control()

        # if statement required to avoid MachineErrors, cleaner than adding
        # transitions to all possible states.
        if self.is_blocked() or self.is_active_stay_on():
            self.enable()

    # =====================================================
    #    T I M E R S
    # =====================================================

    def _start_timer(self):
        self.log.debug("_start_timer :: Light params: %s", self.lightParams)
        if self.backoff_count == 0:
            self.previous_delay = self.lightParams.get(CONF_DELAY, DEFAULT_DELAY)
        else:
            self.log.debug(
                "_start_timer :: Backoff: %s,  count: %s, delay%s, factor: %s",
                self.backoff,
                self.backoff_count,
                self.lightParams.get(CONF_DELAY, DEFAULT_DELAY),
                self.backoff_factor,
            )
            self.previous_delay = round(self.previous_delay * self.backoff_factor, 2)
            if self.previous_delay > self.backoff_max:
                self.log.debug("Max backoff reached. Will not increase further.")
                self.previous_delay = self.backoff_max
            self.update(delay=self.previous_delay)

        self._cancel_timer()
        expiry_time = dt.now() + timedelta(seconds=self.previous_delay)
        self.timer_handle = event.async_call_later(
            self.hass, self.previous_delay, self.timer_expire
        )
        self.update(expires_at=expiry_time)

    def _cancel_timer(self):
        if self.timer_handle is not None:
            self.timer_handle()
            self.timer_handle = None

    def _reset_timer(self):
        self.log.debug("_reset_timer :: Resetting timer: %s", self.backoff)
        self.update(reset_at=dt.now())
        if self.backoff:
            self.backoff_count += 1
            self.update(backoff_count=self.backoff_count)
        self._start_timer()
        return True

    @callback
    def timer_expire(self, _now=None):
        self.timer_handle = None
        if not self._running:
            return
        self.log.debug("timer_expire :: Timer expired")
        if not self.is_released():
            # A duration sensor (or hold sensor) is still on: it overrules the
            # timer, EC stays active until it is released.
            self.update(expires_at="pending sensor")
            self._schedule_hold_check()
        else:
            self.log.debug("timer_expire :: Trigger timer_expires event")
            self._safe_trigger("timer_expires")

    def _cancel_block_timer(self):
        if self.block_timer_handle is not None:
            self.block_timer_handle()
            self.block_timer_handle = None

    def _cancel_hold_check(self):
        if self._hold_check_handle is not None:
            self._hold_check_handle()
            self._hold_check_handle = None

    def _schedule_hold_check(self):
        """The timer expired while sensors still hold the controller: re-check
        when the first of them reaches the maximum hold time."""
        self._cancel_hold_check()
        if not self.max_hold_time:
            return
        now = dt.utcnow()
        deadlines = []
        for entity_id in self._holding_candidates():
            s = self.hass.states.get(entity_id)
            if s is not None and self.matches(s.state, self.SENSOR_ON_STATE):
                deadline = s.last_changed + timedelta(seconds=self.max_hold_time)
                if deadline > now:
                    deadlines.append(deadline)
        if deadlines:
            delay = (min(deadlines) - now).total_seconds() + 1
            self._hold_check_handle = event.async_call_later(self.hass, delay, self._hold_check)

    @callback
    def _hold_check(self, _now=None):
        self._hold_check_handle = None
        if not self._running or not self.is_active_timer() or not self.is_timer_expired():
            return
        if not self.is_released():
            self._schedule_hold_check()
            return
        self.log.info("Maximum hold time reached, the sensors no longer hold the controller")
        self.update(sensor_turned_off_at=dt.now())
        self._release("The maximum hold time was reached")

    @callback
    def block_timer_expire(self, _now=None):
        self.block_timer_handle = None
        if not self._running:
            return
        self.log.debug("block_timer_expire :: Blocked Timer expired")
        self._safe_trigger("block_timer_expires")

    # =====================================================
    # S T A T E   M A C H I N E   C O N D I T I O N S
    # =====================================================

    def _entity_state(self, entity_id: str, kind: str) -> str | None:
        s = self.hass.states.get(entity_id)
        if s is None:
            if entity_id not in self._warned_missing:
                self._warned_missing.add(entity_id)
                self.log.warning(
                    "Potential configuration error: %s entity (%s) does not exist (yet).",
                    kind,
                    entity_id,
                )
            return None
        return s.state

    def _first_matching(self, entities: list[str], on_states: list[str], kind: str) -> str | None:
        for e in entities:
            state = self._entity_state(e, kind)
            if state is not None and self.matches(state, on_states):
                return e
        return None

    def _held_too_long(self, entity_id: str, state: State) -> bool:
        """True when a sensor has been on for longer than the maximum hold time."""
        if not self.max_hold_time:
            return False
        on_for = dt.utcnow() - state.last_changed
        if on_for < timedelta(seconds=self.max_hold_time):
            return False
        key = (entity_id, state.last_changed)
        if key not in self._warned_held_too_long:
            self._warned_held_too_long.add(key)
            self.log.warning(
                "%s has been on for %s, longer than the maximum hold time (%s s): "
                "it no longer keeps the controller active (stuck sensor?)",
                entity_id,
                str(on_for).split(".")[0],
                self.max_hold_time,
            )
        return True

    def _first_sensor_on(self, entities: list[str]) -> str | None:
        """First sensor that is on and not on for longer than the maximum hold time."""
        for e in entities:
            if self._entity_state(e, "Sensor") is None:
                continue
            s = self.hass.states.get(e)
            if self.matches(s.state, self.SENSOR_ON_STATE) and not self._held_too_long(e, s):
                return e
        return None

    def _holding_candidates(self) -> list[str]:
        """Sensors that keep the controller active while they are on."""
        if self.is_duration_sensor():
            return self.holdSensorEntities + self.sensorEntities
        return list(self.holdSensorEntities)

    def _override_entity_state(self):
        e = self._first_matching(self.overrideEntities, self.OVERRIDE_ON_STATE, "Override")
        self.log.debug("Override entities are %s. [%s]", "ON" if e else "OFF", e)
        return e

    def is_override_state_off(self):
        return self._override_entity_state() is None

    def is_override_state_on(self):
        return self._override_entity_state() is not None

    def is_within_grace_period(self):
        """True while state changes are ignored after EC's own service calls."""
        if not self.grace_period:
            return False
        return dt.utcnow() < self.ignore_state_changes_until

    def _sensor_entity_state(self):
        e = self._first_sensor_on(self.sensorEntities + self.holdSensorEntities)
        self.log.debug("Sensor entities are %s. [%s]", "ON" if e else "OFF", e)
        return e

    def is_sensor_off(self):
        return self._sensor_entity_state() is None

    def is_sensor_on(self):
        return self._sensor_entity_state() is not None

    def _holding_sensor(self) -> str | None:
        """Return the sensor that currently keeps EC active, if any.

        Hold sensors always hold. Regular sensors hold only for duration
        sensor types (event sensors are momentary by definition). A sensor on
        for longer than the maximum hold time does not hold.
        """
        return self._first_sensor_on(self._holding_candidates())

    def is_released(self):
        return self._holding_sensor() is None

    def _state_entity_state(self):
        e = self._first_matching(self.stateEntities, self.STATE_ON_STATE, "State")
        self.log.debug("State entities are %s. [%s]", "ON" if e else "OFF", e)
        return e

    def is_state_entities_off(self):
        return self._state_entity_state() is None

    def is_state_entities_on(self):
        return self._state_entity_state() is not None

    def is_block_enabled(self):
        return self.disable_block is False

    def will_stay_on(self):
        return self.stay

    def is_night(self):
        if self.night_mode is None:
            return False  # if night mode is undefined, it's never night :)
        self.log.debug("NIGHT MODE ENABLED: %s", self.night_mode)
        try:
            return self.now_is_between(
                self.night_mode[CONF_START_TIME], self.night_mode[CONF_END_TIME]
            )
        except ValueError as err:
            self.log.error("Invalid night mode time: %s", err)
            return False

    def is_event_sensor(self):
        return self.sensor_type == SENSOR_TYPE_EVENT

    def is_duration_sensor(self):
        return self.sensor_type == SENSOR_TYPE_DURATION

    def is_timer_expired(self):
        return self.timer_handle is None

    def does_sensor_reset_timer(self):
        return bool(self.config.get(CONF_SENSOR_RESETS_TIMER))

    # =====================================================
    # S T A T E   M A C H I N E   C A L L B A C K S
    # =====================================================
    def on_enter_idle(self):
        self.log.debug("Entering idle")
        # Entering idle due to no events, set a new context with no parent
        self.set_context(None)
        self.do_transition_behaviour(CONF_ON_ENTER_IDLE)
        self.entity.reset_state()

    def on_exit_idle(self):
        self.log.debug("Exiting idle")
        self.do_transition_behaviour(CONF_ON_EXIT_IDLE)

    def on_enter_overridden(self):
        self.log.debug("Entering overridden")
        self.do_transition_behaviour(CONF_ON_ENTER_OVERRIDDEN)

    def on_exit_overridden(self):
        self.log.debug("Exiting overridden")
        self.do_transition_behaviour(CONF_ON_EXIT_OVERRIDDEN)

    def on_enter_active(self):
        self.log.debug("Entering active")
        self.update(last_triggered_at=str(dt.now()))
        self.backoff_count = 0
        self.prepare_service_data()

        self.log.debug("on_enter_active :: light params before turning on: %s", self.lightParams)
        self.do_transition_behaviour(CONF_ON_ENTER_ACTIVE)
        self.enter()
        # Only the timer sub-state uses the timer. The original also started
        # it in stay mode, where its expiry raised a MachineError.
        if self.is_active_timer():
            self._start_timer()
        self._delayed_start()

    def on_exit_active(self):
        self.log.debug("Exiting active")
        self.log.debug("on_exit_active :: cancelling timer")
        self._cancel_timer()  # cancel previous timer
        self._cancel_hold_check()
        self._delayed_exit()
        self.update(delay=self.lightParams.get(CONF_DELAY))
        self.do_transition_behaviour(CONF_ON_EXIT_ACTIVE)

    def on_enter_blocked(self):
        self.log.debug("Entering blocked")
        self.update(blocked_at=dt.now())
        self.update(blocked_by=self._state_entity_state())

        self.do_transition_behaviour(CONF_ON_ENTER_BLOCKED)
        self._cancel_block_timer()
        if self.block_timeout:
            self.block_timer_handle = event.async_call_later(
                self.hass, self.block_timeout, self.block_timer_expire
            )
            self.update(block_timeout=self.block_timeout)

    def on_exit_blocked(self):
        self.log.debug("Exiting blocked")
        self.do_transition_behaviour(CONF_ON_EXIT_BLOCKED)
        self._cancel_block_timer()

    def on_enter_constrained(self):
        self.log.debug("Entering constrained")
        self.do_transition_behaviour(CONF_ON_ENTER_CONSTRAINED)

    def on_exit_constrained(self):
        self.log.debug("Exiting constrained")
        self.do_transition_behaviour(CONF_ON_EXIT_CONSTRAINED)

    # =====================================================
    #    C O N F I G U R A T I O N  &  V A L I D A T I O N
    # =====================================================

    def _track(self, entities: list[str], action) -> None:
        if entities:
            self._unsubs.append(
                event.async_track_state_change_event(self.hass, entities, action)
            )

    def config_transition_behaviours(self, config):
        self.transition_behaviours = dict(DEFAULT_BEHAVIOURS)
        self.transition_behaviours.update(config.get(CONF_BEHAVIOURS) or {})
        self.log.debug(
            "config_transition_behaviours :: Transition Behaviours: %s",
            pprint.pformat(self.transition_behaviours),
        )

    def config_control_entities(self, config):
        self.controlEntities = list(config.get(CONF_CONTROL_ENTITIES) or [])
        self.log.debug("Control Entities: %s", self.controlEntities)

    def config_state_entities(self, config):
        self.stateEntities = list(config.get(CONF_STATE_ENTITIES) or [])
        if self.stateEntities:
            self.log.info(
                "State Entities (explicitly defined - I hope you know what you are doing): %s",
                self.stateEntities,
            )
        else:
            # If no state entities are defined, use control entites as state
            self.stateEntities = self.controlEntities.copy()
            self.log.debug("Added Control Entities as state entities (default): %s", self.stateEntities)
        self._track(self.stateEntities, self.state_entity_state_change)

    def config_off_entities(self, config):
        self.triggerOnDeactivate = list(config.get(CONF_TRIGGER_ON_DEACTIVATE) or [])
        if self.triggerOnDeactivate:
            self.log.info("Off Entities: %s", self.triggerOnDeactivate)

    def config_on_entities(self, config):
        self.triggerOnActivate = list(config.get(CONF_TRIGGER_ON_ACTIVATE) or [])
        if self.triggerOnActivate:
            self.log.info("On Entities: %s", self.triggerOnActivate)

    def config_sensor_entities(self, config):
        self.sensorEntities = list(config.get(CONF_SENSORS) or [])
        # A sensor listed as both is a regular (triggering) sensor.
        self.holdSensorEntities = [
            e for e in (config.get(CONF_HOLD_SENSORS) or []) if e not in self.sensorEntities
        ]
        if not self.sensorEntities:
            self.log.error("No sensor entities defined. You must define at least one sensor entity.")
        self.log.debug("Sensor Entities: %s", self.sensorEntities)
        self.log.debug("Hold Sensor Entities: %s", self.holdSensorEntities)
        self._track(self.sensorEntities, self.sensor_state_change)
        self._track(self.holdSensorEntities, self.hold_sensor_state_change)

    def config_static_strings(self, config):
        def pick(key, default):
            # Explicit per-entity-type lists replace the defaults.
            return list(config.get(key) or default)

        self.CONTROL_ON_STATE = pick(CONF_CONTROL_STATES_ON, DEFAULT_STATES_ON)
        self.CONTROL_OFF_STATE = pick(CONF_CONTROL_STATES_OFF, DEFAULT_STATES_OFF)
        self.SENSOR_ON_STATE = pick(CONF_SENSOR_STATES_ON, DEFAULT_STATES_ON)
        self.SENSOR_OFF_STATE = pick(CONF_SENSOR_STATES_OFF, DEFAULT_STATES_OFF)
        self.OVERRIDE_ON_STATE = pick(CONF_OVERRIDE_STATES_ON, DEFAULT_STATES_ON)
        self.OVERRIDE_OFF_STATE = pick(CONF_OVERRIDE_STATES_OFF, DEFAULT_STATES_OFF)
        self.STATE_ON_STATE = pick(CONF_STATE_STATES_ON, DEFAULT_STATES_ON)
        self.STATE_OFF_STATE = pick(CONF_STATE_STATES_OFF, DEFAULT_STATES_OFF)

        # Additional strings are added to every entity type. (The original
        # extended one shared list object several times.)
        for extra, lists in (
            (
                config.get(CONF_STATE_STRINGS_ON) or [],
                (self.CONTROL_ON_STATE, self.SENSOR_ON_STATE, self.OVERRIDE_ON_STATE, self.STATE_ON_STATE),
            ),
            (
                config.get(CONF_STATE_STRINGS_OFF) or [],
                (self.CONTROL_OFF_STATE, self.SENSOR_OFF_STATE, self.OVERRIDE_OFF_STATE, self.STATE_OFF_STATE),
            ),
        ):
            for target in lists:
                target.extend(s for s in extra if s not in target)

    def config_night_mode(self, config):
        """
        Configured night mode parameters. If no night_mode service
        parameters are given, the day mode parameters are used instead.
        """
        night_mode = config.get(CONF_NIGHT_MODE)
        self.night_mode = None
        if not night_mode or not night_mode.get(CONF_ENABLED, True):
            return
        if not night_mode.get(CONF_START_TIME) or not night_mode.get(CONF_END_TIME):
            self.log.error("Night mode requires a start_time and an end_time parameter!")
            return
        # Copy: the set_night_mode service changes it at runtime.
        self.night_mode = dict(night_mode)
        delay = night_mode.get(CONF_DELAY)
        self.light_params_night = {
            CONF_DELAY: delay if delay is not None else self.light_params_day[CONF_DELAY],
            CONF_SERVICE_DATA: night_mode.get(CONF_SERVICE_DATA)
            or self.light_params_day.get(CONF_SERVICE_DATA),
            CONF_SERVICE_DATA_OFF: night_mode.get(CONF_SERVICE_DATA_OFF)
            or self.light_params_day.get(CONF_SERVICE_DATA_OFF),
        }

    def config_state_attributes_ignore(self, config):
        self.ignored_event_sources = list(config.get(CONF_IGNORED_EVENT_SOURCES) or [])
        self.state_attributes_ignore = list(config.get(CONF_STATE_ATTRIBUTES_IGNORE) or [])
        self.log.debug(
            "Ignoring events (state changes) caused by the following entities): %s",
            self.ignored_event_sources,
        )
        self.log.debug(
            "Ignoring state changes on the following attributes: %s",
            self.state_attributes_ignore,
        )

    def config_normal_mode(self, config):
        delay = config.get(CONF_DELAY)
        self.light_params_day = {
            CONF_DELAY: DEFAULT_DELAY if delay is None else delay,
            CONF_SERVICE_DATA: config.get(CONF_SERVICE_DATA) or None,
            CONF_SERVICE_DATA_OFF: config.get(CONF_SERVICE_DATA_OFF) or None,
        }

    @property
    def start_time(self):
        """ Wrapper for _start_time_private """
        return self.debug_time_wrapper(self._start_time_private)

    @property
    def end_time(self):
        """ Wrapper for _end_time_private """
        return self.debug_time_wrapper(self._end_time_private)

    def config_times(self, config):
        self._start_time_private = None
        self._end_time_private = None
        if config.get(CONF_START_TIME) and config.get(CONF_END_TIME):
            # FOR OPTIONAL DEBUGGING: for initial setup use the raw input value
            self._start_time_private = config.get(CONF_START_TIME)
            self._end_time_private = config.get(CONF_END_TIME)

            try:
                parsed_start = self.parse_time(self.start_time, aware=False)
                parsed_end = self.parse_time(self.end_time, aware=False)
            except ValueError as err:
                self.log.error("Invalid start_time/end_time, constraints disabled: %s", err)
                self._start_time_private = self._end_time_private = None
                self.log_config()
                return
            # FOR OPTIONAL DEBUGGING: subsequently use normal delay
            sparts = re.search(r"^(now\s*[+-]\s*\d+)", config.get(CONF_START_TIME))
            if sparts is not None:
                self._start_time_private = sparts.group(1)
            eparts = re.search(r"^(now\s*[+-]\s*\d+)", config.get(CONF_END_TIME))
            if eparts is not None:
                self._end_time_private = eparts.group(1)

            self.update(start=self.start_time)
            self.update(end=self.end_time)

            parsed_start = self.futurize(parsed_start)
            parsed_end = self.futurize(parsed_end)
            self.log.debug("Setting FIRST START callback for %s", parsed_start)
            self.log.debug("Setting FIRST END callback for %s", parsed_end)
            # Publish the next window edges right away (WimImmelman fork).
            self.update(start_time=parsed_start, end_time=parsed_end)

            self._schedule_start(parsed_start)
            self._schedule_end(parsed_end)

            if not self.now_is_between(self.start_time, self.end_time):
                self.log.debug("Constrain period active. Transition to 'constrained'")
                if not self.is_constrained():
                    self.constrain()

        self.log_config()

    def _schedule_start(self, when):
        self._cancel_time_callbacks(start=True, end=False)
        self._start_unsub = event.async_track_point_in_time(
            self.hass, self.start_time_callback, when
        )

    def _schedule_end(self, when):
        self._cancel_time_callbacks(start=False, end=True)
        self._end_unsub = event.async_track_point_in_time(
            self.hass, self.end_time_callback, when
        )

    def _cancel_time_callbacks(self, start=True, end=True):
        if start and self._start_unsub is not None:
            self._start_unsub()
            self._start_unsub = None
        if end and self._end_unsub is not None:
            self._end_unsub()
            self._end_unsub = None

    def config_override_entities(self, config):
        self.overrideEntities = list(config.get(CONF_OVERRIDES) or [])
        if self.overrideEntities:
            self.log.debug("Override Entities: %s", self.overrideEntities)
            self._track(self.overrideEntities, self.override_state_change)

    def config_other(self, config):
        self.block_timeout = config.get(CONF_BLOCK_TIMEOUT) or None
        self.grace_period = config.get(CONF_GRACE_PERIOD) or None
        self.max_hold_time = config.get(CONF_MAX_HOLD_TIME) or None
        self.delayedEntities = list(config.get(CONF_DELAYED_ENTITIES) or [])
        self.delayed_after = config.get(CONF_DELAYED_AFTER) or 0
        self.delayed_min_on = config.get(CONF_DELAYED_MIN_ON) or 0
        self.disable_block = bool(config.get(CONF_DISABLE_BLOCK, False))
        self.backoff = bool(config.get(CONF_BACKOFF, False))
        self.stay = bool(config.get(CONF_STAY_MODE, False))

        if self.backoff:
            self.log.debug("config_other :: setting up backoff. Using delay as initial backoff value.")
            self.backoff_factor = config.get(CONF_BACKOFF_FACTOR) or DEFAULT_BACKOFF_FACTOR
            self.backoff_max = config.get(CONF_BACKOFF_MAX) or DEFAULT_BACKOFF_MAX

        sensor_type = config.get(CONF_SENSOR_TYPE) or SENSOR_TYPE_EVENT
        self.sensor_type = (
            SENSOR_TYPE_DURATION if sensor_type == SENSOR_TYPE_DURATION else SENSOR_TYPE_EVENT
        )
        self.update(sensor_type=self.sensor_type)

    # =====================================================
    #    E V E N T   C A L L B A C K S
    # =====================================================

    @callback
    def end_time_callback(self, evt):
        """
            Called when `end_time` is reached, will change state to `constrained` and schedule `end_time` callback.
        """
        self.log.debug("end_time_callback :: Triggered")
        try:
            # must be reparsed to get up to date sunset/sunrise times
            parsed_end = self.futurize(self.parse_time(self.end_time))
            self.log.debug("end_time_callback :: New callback set to %s (future)", parsed_end)
            self._schedule_end(parsed_end)
            self.update(end_time=parsed_end)
        except ValueError as err:
            self.log.error("end_time_callback :: %s", err)

        # The original also ran the on_enter_constrained behaviour here, so it
        # was executed twice (once more by on_enter_constrained).
        if not self.is_constrained():
            self._safe_trigger("constrain")

    @callback
    def start_time_callback(self, evt):
        """
            Called when `start_time` is reached, will change state to `idle` and schedule `start_time` callback.
        """
        self.log.debug("start_time_callback :: Triggered")
        try:
            # must be reparsed to get up to date sunset/sunrise times
            parsed_start = self.futurize(self.parse_time(self.start_time))
            self.log.debug("start_time_callback :: New callback set to %s (future)", parsed_start)
            self._schedule_start(parsed_start)
            self.update(start_time=parsed_start)
        except ValueError as err:
            self.log.error("start_time_callback :: %s", err)

        self._apply_start_time_transition()

    def _apply_start_time_transition(self):
        """Transition the machine when start_time is reached. Never raises."""
        if self.is_overridden() and self.is_override_state_on():
            self.log.debug("start_time_callback :: Override is still active; staying overridden")
            return
        if self.is_constrained() and self.overrideEntities and self.is_override_state_on():
            # An override that switched on while constrained was never seen by
            # the machine; honour it now (pluskal fork).
            self.update(overridden_by=self._override_entity_state())
            self._safe_trigger("enable")
            self.update(overridden_at=str(dt.now()))
        elif self.is_state_entities_on() and self.is_block_enabled():
            self._safe_trigger("blocked")
        else:
            # If the entity is on and block is disabled, we transition from
            # constrained to idle.
            self._safe_trigger("enable")

    # =====================================================
    #    H E L P E R   F U N C T I O N S        ( N E W )
    # =====================================================

    def _render_templates(self, value):
        """Render Home Assistant templates in service data, e.g.
        `brightness_pct: "{{ 50 if is_state('input_boolean.dnd', 'on') else 100 }}"`.
        A key whose template fails is left out (and logged)."""
        if isinstance(value, dict):
            rendered = {}
            for key, item in value.items():
                try:
                    rendered[key] = self._render_templates(item)
                except TemplateError as err:
                    self.log.error("Service data '%s' could not be rendered: %s", key, err)
            return rendered
        if isinstance(value, list):
            return [self._render_templates(item) for item in value]
        if isinstance(value, str) and template.is_template_string(value):
            return template.Template(value, self.hass).async_render(parse_result=True)
        return value

    # Delayed entities: turned on once the controller has been active for
    # delayed_after seconds, then kept on for at least delayed_min_on seconds
    # (even if the controller goes idle meanwhile) and after that for as long
    # as the controller stays active.

    def _cancel_delayed(self):
        if self._delayed_handle is not None:
            self._delayed_handle()
            self._delayed_handle = None

    def _delayed_status(self, status: str, until: datetime | None = None) -> None:
        """Show what the delayed entities are doing (entity attributes):
        off, waiting (until = turn-on time), running (until = end of the
        minimum time) or running_until_idle."""
        attributes = self.entity.attributes
        attributes["delayed_status"] = status
        if until is None:
            attributes.pop("delayed_until", None)
        else:
            attributes["delayed_until"] = dt.as_local(until)
        self.entity.do_update()

    def _delayed_start(self):
        if self.delayedEntities and not self._delayed_running and self._delayed_handle is None:
            self._delayed_handle = event.async_call_later(
                self.hass, self.delayed_after, self._delayed_turn_on
            )
            self._delayed_status("waiting", dt.utcnow() + timedelta(seconds=self.delayed_after))

    @callback
    def _delayed_turn_on(self, _now=None):
        self._delayed_handle = None
        if not self._running or not self.is_active(allow_substates=True):
            return
        # Entities somebody already switched on are left alone.
        self._delayed_running = [
            e
            for e in self.delayedEntities
            if not self.matches(self._entity_state(e, "Delayed"), self.CONTROL_ON_STATE)
        ]
        if not self._delayed_running:
            self._delayed_status("off")
            return
        for e in self._delayed_running:
            self.call_service(e, "turn_on")
        self._delayed_schedule_min(self.delayed_min_on)

    def _delayed_schedule_min(self, seconds: float) -> None:
        self._delayed_min_done = False
        self._delayed_min_until = dt.utcnow() + timedelta(seconds=seconds)
        self._delayed_handle = event.async_call_later(
            self.hass, seconds, self._delayed_min_expired
        )
        self._delayed_status("running", self._delayed_min_until)

    @callback
    def _delayed_min_expired(self, _now=None):
        self._delayed_handle = None
        self._delayed_min_done = True
        self._delayed_min_until = None
        if not self.is_active(allow_substates=True):
            self._delayed_turn_off()
        else:
            self._delayed_status("running_until_idle")

    def _delayed_exit(self):
        """The controller leaves active (nobody there any more)."""
        if not self._delayed_running:
            if self._delayed_handle is not None:
                self._cancel_delayed()  # left before delayed_after: never turn on
                self._delayed_status("off")
        elif self._delayed_min_done:
            self._delayed_turn_off()
        # else: _delayed_min_expired turns them off

    def _delayed_turn_off(self):
        for e in self._delayed_running:
            self.call_service(e, "turn_off")
        self._delayed_running = []
        self._delayed_status("off")

    def delayed_restore_data(self) -> dict[str, Any]:
        """Running delayed entities, saved by the entity across reloads and restarts."""
        until = None if self._delayed_min_done else self._delayed_min_until
        return {
            "delayed_running": list(self._delayed_running),
            "delayed_min_until": until.isoformat() if until else None,
        }

    def _delayed_restore(self) -> None:
        """Take over delayed entities that were running before a reload/restart."""
        data = self.restored_extra or {}
        running = [
            e
            for e in data.get("delayed_running") or []
            if e in self.delayedEntities
            and self.matches(self._entity_state(e, "Delayed"), self.CONTROL_ON_STATE)
        ]
        if not running:
            return
        self._delayed_running = running
        until = dt.parse_datetime(data["delayed_min_until"]) if data.get("delayed_min_until") else None
        remaining = (until - dt.utcnow()).total_seconds() if until else 0
        # Expired minimum: fires right away and turns them off unless active.
        self._delayed_schedule_min(max(remaining, 0))

    def handleTriggerOnDeactivateEntities(self):
        """ Entities that are defined outside of control entities via the `triggerOnDetivate` key. """
        if self.triggerOnDeactivate:
            self.log.info("handleTriggerOnDeactivateEntities :: Triggering Deactivation entities")
            for e in self.triggerOnDeactivate:
                if self.lightParams.get(CONF_SERVICE_DATA_OFF) is not None:
                    self.call_service(e, "turn_on", **self.lightParams.get(CONF_SERVICE_DATA_OFF))
                else:
                    self.call_service(e, "turn_on")

    def handleTriggerOnActivateEntities(self):
        """ Entities that are defined outside of control entities via the `triggerOnActivate` key. """
        if self.triggerOnActivate:
            self.log.info("handleTriggerOnActivateEntities :: Triggering Activation entities")
            for e in self.triggerOnActivate:
                if self.lightParams.get(CONF_SERVICE_DATA) is not None:
                    self.call_service(e, "turn_on", **self.lightParams.get(CONF_SERVICE_DATA))
                else:
                    self.call_service(e, "turn_on")

    def turn_on_control_entities(self):
        self.handleTriggerOnActivateEntities()

        for e in self.controlEntities:
            if self.lightParams.get(CONF_SERVICE_DATA) is not None:
                self.log.debug(
                    "turn_on_control_entities :: Turning on %s with service parameters %s",
                    e,
                    self.lightParams.get(CONF_SERVICE_DATA),
                )
                self.call_service(e, "turn_on", **self.lightParams.get(CONF_SERVICE_DATA))
            else:
                self.log.debug(
                    "turn_on_control_entities :: Turning on %s (no parameters passed to service call)", e
                )
                self.call_service(e, "turn_on")

    def turn_off_control_entities(self):
        self.handleTriggerOnDeactivateEntities()
        for e in self.controlEntities:
            self.log.debug("turn_off_control_entities :: Turning off %s", e)

            if self.lightParams.get(CONF_SERVICE_DATA_OFF) is not None:
                self.call_service(e, "turn_off", **self.lightParams.get(CONF_SERVICE_DATA_OFF))
            else:
                self.call_service(e, "turn_off")

    def now_is_between(self, start_time_str, end_time_str, name=None):
        start_time = (self._parse_time(start_time_str, name))["datetime"]
        end_time = (self._parse_time(end_time_str, name))["datetime"]
        now = dt.as_local(dt.now())
        start_date = now.replace(
            hour=start_time.hour, minute=start_time.minute, second=start_time.second
        )
        end_date = now.replace(
            hour=end_time.hour, minute=end_time.minute, second=end_time.second
        )
        if end_date < start_date:
            # Spans midnight
            if now < start_date and now < end_date:
                now = now + timedelta(days=1)
            end_date = end_date + timedelta(days=1)

        self.log.debug("now_is_between start time %s", start_date)
        self.log.debug("now_is_between end time %s", end_date)
        return start_date <= now <= end_date

    def parse_time(self, time_str, name=None, aware=False):
        if aware is True:
            return dt.as_local(self._parse_time(time_str, name)["datetime"]).time()
        return self.make_naive((self._parse_time(time_str, name))["datetime"]).time()

    def parse_datetime(self, time_str, name=None, aware=False):
        if aware is True:
            return dt.as_local(self._parse_time(time_str, name)["datetime"])
        return self.make_naive(dt.as_local(self._parse_time(time_str, name)["datetime"]))

    def _parse_time(self, time_str, name=None):
        parsed_time = None
        sun = None
        offset = 0
        time_str = str(time_str).strip()
        parts = re.search(r"^(\d+)-(\d+)-(\d+)\s+(\d+):(\d+):(\d+)$", time_str)
        if parts:
            this_time = datetime(
                int(parts.group(1)),
                int(parts.group(2)),
                int(parts.group(3)),
                int(parts.group(4)),
                int(parts.group(5)),
                int(parts.group(6)),
                0,
            )
            parsed_time = dt.as_local(this_time)
        else:
            parts = re.search(r"^(\d+):(\d+)(?::(\d+))?$", time_str)
            if parts:
                today = dt.as_local(dt.now())
                time_temp = time(
                    int(parts.group(1)), int(parts.group(2)), int(parts.group(3) or 0), 0
                )
                parsed_time = today.replace(
                    hour=time_temp.hour,
                    minute=time_temp.minute,
                    second=time_temp.second,
                    microsecond=0,
                )
            else:
                parts = re.search(
                    r"^(sunrise|sunset)(?:\s*([+-])\s*(\d+):(\d+)(?::(\d+))?)?$", time_str
                )
                if parts:
                    sun = parts.group(1)
                    base = self.sunrise(True) if sun == "sunrise" else self.sunset(True)
                    if base is None:
                        raise ValueError(f"{sun} does not occur today at this location")
                    if parts.group(2):
                        td = timedelta(
                            hours=int(parts.group(3)),
                            minutes=int(parts.group(4)),
                            seconds=int(parts.group(5) or 0),
                        )
                        if parts.group(2) == "+":
                            offset = td.total_seconds()
                            parsed_time = base + td
                        else:
                            offset = td.total_seconds() * -1
                            parsed_time = base - td
                    else:
                        parsed_time = base
        if parsed_time is None:
            if name is not None:
                raise ValueError(f"{name}: invalid time string: {time_str}")
            raise ValueError(f"invalid time string: {time_str}")
        return {"datetime": parsed_time, "sun": sun, "offset": offset}

    def make_naive(self, dts):
        local = dt.as_local(dts)
        return datetime(
            local.year,
            local.month,
            local.day,
            local.hour,
            local.minute,
            local.second,
            local.microsecond,
        )

    def sunset(self, aware):
        t = get_astral_event_date(self.hass, SUN_EVENT_SUNSET, dt.now().date())
        if t is not None and aware is True:
            return dt.as_local(t)
        return t

    def sunrise(self, aware):
        t = get_astral_event_date(self.hass, SUN_EVENT_SUNRISE, dt.now().date())
        if t is not None and aware is True:
            return dt.as_local(t)
        return t

    def prepare_service_data(self):
        """
            Called when entering active state and on initial set up to set
            correct service parameters.
        """
        if self.is_night():
            self.log.debug("Using NIGHT MODE parameters: %s", self.light_params_night)
            self.lightParams = self.light_params_night
            self.update(mode=MODE_NIGHT)
        else:
            self.log.debug("Using DAY MODE parameters: %s", self.light_params_day)
            self.lightParams = self.light_params_day
            if self.night_mode is not None:
                self.update(mode=MODE_DAY)  # only show when night mode set up
        self.update(delay=self.lightParams.get(CONF_DELAY))

    def call_service(self, entity, service, **service_data):
        """ Helper for calling HA services with the correct parameters """
        self.log.debug("call_service :: Calling service %s on %s", service, entity)
        if self.grace_period:
            self.ignore_state_changes_until = dt.utcnow() + timedelta(seconds=self.grace_period)

        domain = entity.split(".")[0]
        if service in ["turn_on", "turn_off"] and domain in self.homeassistant_turn_on_domains:
            domain = "homeassistant"
            self.log.debug(
                "call_service :: Actually calling service %s on %s via the %s domain because the entity domain requires it.",
                service,
                entity,
                domain,
            )
        service_data = self._render_templates(service_data)
        params = dict(service_data)
        params["entity_id"] = entity
        # Service calls run as tasks on the event loop once the current
        # transition has completed (not eagerly, so the resulting state
        # changes never re-enter a transition in progress). Failures are
        # logged (the original silently discarded them).
        self.hass.async_create_task(
            self._async_call_service(domain, service, params, self.context),
            f"{DOMAIN} {self.name} {domain}.{service}",
            eager_start=False,
        )
        self.update(service_data=service_data)

    async def _async_call_service(self, domain, service, params, context):
        try:
            await self.hass.services.async_call(
                domain, service, params, blocking=True, context=context
            )
        except ServiceNotFound:
            self.log.warning(
                "Service %s.%s does not exist (entity %s)", domain, service, params.get("entity_id")
            )
        except Exception as err:  # noqa: BLE001 - background call, report and continue
            # e.g. service data the entity does not support. The exception type
            # depends on the HA version (voluptuous/probatio/HomeAssistantError).
            self.log.error(
                "Calling %s.%s for %s failed: %s", domain, service, params.get("entity_id"), err
            )

    def set_context(self, parent: Context | None = None) -> None:
        """Set the context used when calling other services.

        The new ID is linked to the context (`parent`) of the triggering event
        and will be unique per trigger.
        """
        unique_id = uuid_util.random_uuid_hex()
        # Restrict id length to database field size
        context_id = f"{self._context_prefix}{unique_id}"[:CONTEXT_ID_CHARACTER_LIMIT]
        self.context_id = context_id
        # parent_id only exists for a non-None parent
        parent_id = parent.id if parent else None
        self.context = Context(parent_id=parent_id, id=context_id)
        # Set the EC entity's context so the logbook can identify the source of
        # events that will be generated by this object.
        self.entity.async_set_context(self.context)

    def is_ignored_context(self, context: Context | None) -> bool:
        """Should the event with the given `context` be ignored?"""
        if context is None:
            return False
        if any(
            re.match(pattern + r"\b", context.id) is not None
            for pattern in self.ignored_event_sources
        ):
            # Matched an ignore_event_source regex pattern
            return True
        # Only events caused by THIS controller are ignored. The original
        # ignored every EC-generated event, so controllers sharing a light
        # never saw each other's changes and could stay blocked forever.
        if context.id.startswith(self._context_prefix):
            return True
        if context.parent_id and context.parent_id.startswith(self._context_prefix):
            return True
        return False

    def matches(self, value, list):
        """Checks whether a string is contained in a list (used for matching state strings)"""
        return value is not None and value in list

    def futurize(self, timet):
        """ Returns tomorrows time if time is in the past.

        Compares in Home Assistant local wall time, not the OS timezone
        (pluskal fork: a mismatch made callbacks re-fire in a tight loop).
        """
        now_local = dt.as_local(dt.now()).replace(tzinfo=None)
        today = now_local.date()
        try:
            t = datetime.combine(today, timet)
        except TypeError:
            t = timet
        if t.tzinfo is not None:
            t = dt.as_local(t).replace(tzinfo=None)
        while t <= now_local:
            if self.debug_day_length:
                t = t + timedelta(seconds=int(self.debug_day_length))
            else:
                t = t + timedelta(1)  # tomorrow!
        return t

    def debug_time_wrapper(self, timet):
        """
            Injects some debugging capability. Number is parenthesis is the
            first delay used on initial component setup. (This creates a time
            difference between start and end time callbacks.)

            The other number after the + sign is the standard period.
            In real life, this would be 24 hours, for debugging you can make
            it a few seconds to see the app change from idle to constrained.

            start_time: now + 5 (3)
            end_time: now + 5 (6)

            This function is used to wrap CONF_START_TIME and CONF_END_TIME
            and should only be called by the corresponding class properties!

            See config_times.
        """
        if timet is None:
            return None
        s = timet
        parts = re.search(r"^now\s*([+-])\s*(\d+)\s*\(?(\d+)?\)?$", timet)
        if parts:
            sign = parts.group(1)
            first_delay = parts.group(3)
            delay = parts.group(2)
            now = dt.now()
            delta = timedelta(seconds=int(delay))
            if first_delay is not None:
                delta = timedelta(seconds=int(first_delay))
            if sign == "-":
                now = now - delta
            else:
                now = now + delta
            s = str(self.make_naive(now).time().replace(microsecond=0))
        return s

    def log_config(self):
        if not self.log.isEnabledFor(logging.DEBUG):
            return
        self.log.debug("--------------------------------------------------")
        self.log.debug("       C O N F I G U R A T I O N   D U M P        ")
        self.log.debug("--------------------------------------------------")
        self.log.debug("Entity Controller       %s", self.name)
        self.log.debug("Sensor Entities         %s", self.sensorEntities)
        self.log.debug("Hold Sensor Entities    %s", self.holdSensorEntities)
        self.log.debug("Control Entities:       %s", self.controlEntities)
        self.log.debug("State Entities:         %s", self.stateEntities)
        self.log.debug("Override Entities:      %s", self.overrideEntities)
        self.log.debug("Activate Trigger E.:    %s", self.triggerOnActivate)
        self.log.debug("Deactivate Trigger E.:  %s", self.triggerOnDeactivate)
        self.log.debug("Ignored state attrs:    %s", self.state_attributes_ignore)
        self.log.debug("Light params:           %s", self.lightParams)
        self.log.debug("Sensor type:            %s", self.sensor_type)
        self.log.debug("        -------        Time        -------        ")
        self.log.debug("Start time:             %s", self._start_time_private)
        self.log.debug("End time:               %s", self._end_time_private)
        self.log.debug("HA Now:                 %s", dt.now())
        self.log.debug("Sunrise:                %s", self.sunrise(True))
        self.log.debug("Sunset:                 %s", self.sunset(True))
        self.log.debug("Transition Behaviours:  %s", self.transition_behaviours)
        self.log.debug("--------------------------------------------------")

    def get_transition_behaviour(self, key):
        """ manages transition_behaviour map """
        return self.transition_behaviours.get(key)

    def do_transition_behaviour(self, behaviour):
        """ Wrapper method for acting on transition behaviours such as at time of end constraint of state transitions from override state. """
        action = self.get_transition_behaviour(behaviour)
        if not action or action == CONF_TRANSITION_BEHAVIOUR_IGNORE:
            return
        if self._suppress_behaviours:
            self.log.debug("%10s | Skipping action '%s' (resuming state)", behaviour, action)
            return
        self.log.debug("%10s | Performing Action - %s", behaviour, action)
        if action == CONF_TRANSITION_BEHAVIOUR_ON:
            self.turn_on_control_entities()
        elif action == CONF_TRANSITION_BEHAVIOUR_OFF:
            self.turn_off_control_entities()
