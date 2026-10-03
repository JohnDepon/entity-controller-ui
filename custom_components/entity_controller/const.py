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
""" Constants used by other files """

DOMAIN = "entity_controller"
DOMAIN_SHORT = "ec"

# Platforms of the standard HA domains set up for every controller (the
# controller entity itself lives in the entity_controller domain).
PLATFORMS = ["button", "switch"]

# Dispatcher signal sent after a controller state write, formatted with the entry id.
SIGNAL_CONTROLLER_UPDATED = "entity_controller_updated_{}"


# services
SERVICE_ACTIVATE = "activate"
SERVICE_CLEAR_BLOCK = "clear_block"
SERVICE_ENABLE_BLOCK = "enable_block"
SERVICE_ENABLE_STAY_MODE = "enable_stay_mode"
SERVICE_DISABLE_STAY_MODE = "disable_stay_mode"
SERVICE_SET_NIGHT_MODE = "set_night_mode"

#configuration
CONF_START_TIME = 'start_time'
CONF_END_TIME = 'end_time'

# Transition Behaviours
CONF_BEHAVIOURS = 'behaviours'

CONF_ON_ENTER_IDLE='on_enter_idle'
CONF_ON_EXIT_IDLE='on_exit_idle'
CONF_ON_ENTER_ACTIVE='on_enter_active'
CONF_ON_EXIT_ACTIVE='on_exit_active'
CONF_ON_ENTER_OVERRIDDEN = 'on_enter_overridden'
CONF_ON_EXIT_OVERRIDDEN = 'on_exit_overridden'
CONF_ON_ENTER_CONSTRAINED = 'on_enter_constrained'
CONF_ON_EXIT_CONSTRAINED = 'on_exit_constrained'
CONF_ON_ENTER_BLOCKED = 'on_enter_blocked'
CONF_ON_EXIT_BLOCKED = 'on_exit_blocked'

CONF_TRANSITION_BEHAVIOUR_ON = 'on'
CONF_TRANSITION_BEHAVIOUR_OFF = 'off'
CONF_TRANSITION_BEHAVIOUR_IGNORE = 'ignore'
TRANSITION_BEHAVIOUR_OPTIONS = [
    CONF_TRANSITION_BEHAVIOUR_ON,
    CONF_TRANSITION_BEHAVIOUR_OFF,
    CONF_TRANSITION_BEHAVIOUR_IGNORE,
]
# Ordered as they are shown in the UI. The value is the default behaviour.
DEFAULT_BEHAVIOURS = {
    CONF_ON_ENTER_IDLE: CONF_TRANSITION_BEHAVIOUR_OFF,
    CONF_ON_EXIT_IDLE: CONF_TRANSITION_BEHAVIOUR_IGNORE,
    CONF_ON_ENTER_ACTIVE: CONF_TRANSITION_BEHAVIOUR_ON,
    CONF_ON_EXIT_ACTIVE: CONF_TRANSITION_BEHAVIOUR_IGNORE,
    CONF_ON_ENTER_OVERRIDDEN: CONF_TRANSITION_BEHAVIOUR_IGNORE,
    CONF_ON_EXIT_OVERRIDDEN: CONF_TRANSITION_BEHAVIOUR_IGNORE,
    CONF_ON_ENTER_CONSTRAINED: CONF_TRANSITION_BEHAVIOUR_IGNORE,
    CONF_ON_EXIT_CONSTRAINED: CONF_TRANSITION_BEHAVIOUR_IGNORE,
    CONF_ON_ENTER_BLOCKED: CONF_TRANSITION_BEHAVIOUR_IGNORE,
    CONF_ON_EXIT_BLOCKED: CONF_TRANSITION_BEHAVIOUR_IGNORE,
}

SENSOR_TYPE_DURATION = "duration"
SENSOR_TYPE_EVENT = "event"
MODE_DAY = "day"
MODE_NIGHT = "night"

DEFAULT_DELAY = 180
DEFAULT_BRIGHTNESS = 100
DEFAULT_NAME = "Entity Timer"
DEFAULT_BACKOFF_FACTOR = 1.1
DEFAULT_BACKOFF_MAX = 300

# CONF_NAME = 'slug'
CONF_CONTROL_ENTITIES = "entities"
CONF_CONTROL_ENTITY = "entity"
CONF_TRIGGER_ON_ACTIVATE = "trigger_on_activate"
CONF_TRIGGER_ON_DEACTIVATE = "trigger_on_deactivate"
CONF_SENSOR = "sensor"
CONF_SENSORS = "sensors"
CONF_HOLD_SENSORS = "hold_sensors"
# Seconds after which a sensor that is still on no longer keeps the controller
# active (protection against stuck sensors). None = no limit.
CONF_MAX_HOLD_TIME = "max_hold_time"
# Name of the same option in the pluskal fork, accepted by the YAML import.
CONF_HOLD_MAX_SECONDS = "hold_max_seconds"
CONF_SERVICE_DATA = "service_data"
CONF_SERVICE_DATA_ON = "service_data_on"
CONF_SERVICE_DATA_OFF = "service_data_off"
CONF_STATE_ENTITIES = "state_entities"
CONF_STATE_ENTITY = "state_entity"
CONF_OVERRIDE = "override"
CONF_OVERRIDES = "overrides"
CONF_DELAY = "delay"
CONF_BLOCK_TIMEOUT = "block_timeout"
CONF_DISABLE_BLOCK = "disable_block"
CONF_SENSOR_TYPE_DURATION = "sensor_type_duration"
CONF_SENSOR_TYPE = "sensor_type"
CONF_SENSOR_RESETS_TIMER = "sensor_resets_timer"
CONF_NIGHT_MODE = "night_mode"
# Night mode settings are kept when night mode is switched off in the UI.
CONF_ENABLED = "enabled"
CONF_STATE_ATTRIBUTES_IGNORE = "state_attributes_ignore"
CONF_IGNORED_EVENT_SOURCES = "ignored_event_sources"
CONF_STAY_MODE = "stay_mode"
CONF_BACKOFF = "backoff"
CONF_BACKOFF_FACTOR = "backoff_factor"
CONF_BACKOFF_MAX = "backoff_max"
CONF_FRIENDLY_NAME = "friendly_name"
CONF_STATE_STRINGS_ON = "state_strings_on"
CONF_STATE_STRINGS_OFF = "state_strings_off"
CONF_CONTROL_STATES_ON = "control_states_on"
CONF_CONTROL_STATES_OFF = "control_states_off"
CONF_SENSOR_STATES_ON = "sensor_states_on"
CONF_SENSOR_STATES_OFF = "sensor_states_off"
CONF_OVERRIDE_STATES_ON = "override_states_on"
CONF_OVERRIDE_STATES_OFF = "override_states_off"
CONF_STATE_STATES_ON = "state_states_on"
CONF_STATE_STATES_OFF = "state_states_off"
# Debugging aid: overrides the length of a "day" (seconds) used to reschedule
# time constraint callbacks. Only available through YAML.
CONF_DAY_LENGTH = "day_length"

STATE_STRING_KEYS = [
    CONF_CONTROL_STATES_ON,
    CONF_CONTROL_STATES_OFF,
    CONF_SENSOR_STATES_ON,
    CONF_SENSOR_STATES_OFF,
    CONF_OVERRIDE_STATES_ON,
    CONF_OVERRIDE_STATES_OFF,
    CONF_STATE_STATES_ON,
    CONF_STATE_STATES_OFF,
]
DEFAULT_STATES_ON = ["on", "playing", "home", "True"]
DEFAULT_STATES_OFF = ["off", "idle", "paused", "away", "False"]

CONSTRAIN_START = 1
CONSTRAIN_END = 2
STATES = ['pending', 'idle', 'overridden', 'constrained', 'blocked',
          {'name': 'active', 'children': ['timer', 'stay_on'],
           'initial': False}]
# Seconds to ignore state changes of state entities after EC itself called a
# service. Fallback for integrations that do not propagate the HA context of
# the service call to the resulting state change (e.g. some cloud gateways).
CONF_IGNORE_STATE_CHANGES_UNTIL = "grace_period"
CONF_GRACE_PERIOD = CONF_IGNORE_STATE_CHANGES_UNTIL

# Delay before EC starts monitoring entities when Home Assistant is booting.
STARTUP_DELAY = 70
# Delay before EC starts monitoring entities when a controller is (re)loaded
# while Home Assistant is already running (e.g. after saving its options).
RELOAD_DELAY = 1

CONTEXT_ID_CHARACTER_LIMIT = 26

# Config entry keys that are not controller options
CONF_YAML_KEY = "yaml_key"
CONF_ENTITY_ID = "entity_id"
