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
"""UI configuration of Entity Controller.

Creating a controller asks for the basics and then offers a menu with one
form per group of options. Editing a controller (Configure) shows the same
menu. Every option of the YAML configuration is available.
"""

import copy
import re
from dataclasses import dataclass
from typing import Any, Callable

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BACKOFF,
    CONF_BACKOFF_FACTOR,
    CONF_BACKOFF_MAX,
    CONF_BEHAVIOURS,
    CONF_BLOCK_TIMEOUT,
    CONF_CONTROL_ENTITIES,
    CONF_DELAY,
    CONF_DISABLE_BLOCK,
    CONF_ENABLED,
    CONF_END_TIME,
    CONF_ENTITY_ID,
    CONF_GRACE_PERIOD,
    CONF_HOLD_SENSORS,
    CONF_IGNORED_EVENT_SOURCES,
    CONF_MAX_HOLD_TIME,
    CONF_NIGHT_MODE,
    CONF_OVERRIDES,
    CONF_SENSOR_RESETS_TIMER,
    CONF_SENSOR_TYPE,
    CONF_SENSORS,
    CONF_SERVICE_DATA,
    CONF_SERVICE_DATA_OFF,
    CONF_START_TIME,
    CONF_STATE_ATTRIBUTES_IGNORE,
    CONF_STATE_ENTITIES,
    CONF_STATE_STRINGS_OFF,
    CONF_STATE_STRINGS_ON,
    CONF_STAY_MODE,
    CONF_TRIGGER_ON_ACTIVATE,
    CONF_TRIGGER_ON_DEACTIVATE,
    CONF_YAML_KEY,
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_BACKOFF_MAX,
    DEFAULT_BEHAVIOURS,
    DEFAULT_DELAY,
    DEFAULT_STATES_OFF,
    DEFAULT_STATES_ON,
    DOMAIN,
    SENSOR_TYPE_DURATION,
    SENSOR_TYPE_EVENT,
    STATE_STRING_KEYS,
    TRANSITION_BEHAVIOUR_OPTIONS,
)
from .options import complete_options, default_options, normalize_time_string, validate_options

CONF_NAME = "name"

# Attributes that commonly change without anybody touching the light.
COMMON_IGNORED_ATTRIBUTES = [
    "brightness",
    "color_temp",
    "color_temp_kelvin",
    "hs_color",
    "rgb_color",
    "rgbw_color",
    "rgbww_color",
    "xy_color",
    "color_mode",
    "effect",
    "linkquality",
    "last_seen",
    "update",
    "voltage",
]

# --------------------------------------------------------------------------
# Selectors
# --------------------------------------------------------------------------

ENTITIES = selector.EntitySelector(selector.EntitySelectorConfig(multiple=True))
BOOLEAN = selector.BooleanSelector()
TEXT = selector.TextSelector()
OBJECT = selector.ObjectSelector()


def _seconds(minimum: float = 0) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=604800,
            step=1,
            unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _strings(options: list[str]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            multiple=True,
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


SENSOR_TYPE = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[SENSOR_TYPE_EVENT, SENSOR_TYPE_DURATION],
        translation_key="sensor_type",
        mode=selector.SelectSelectorMode.LIST,
    )
)
BEHAVIOUR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=TRANSITION_BEHAVIOUR_OPTIONS,
        translation_key="behaviour",
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
BACKOFF_FACTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0.01, max=10, step=0.01, mode=selector.NumberSelectorMode.BOX)
)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v).strip() for v in value if str(v).strip()]


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    value = int(float(value))
    return value or None


def _dict_or_error(value: Any) -> dict[str, Any] | None:
    """Return the service data mapping, or None when it is not a mapping."""
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return copy.deepcopy(value)
    return None


def _drop_empty(values: dict[str, Any]) -> dict[str, Any]:
    """Remove empty values so optional fields are shown empty in the form."""
    return {k: v for k, v in values.items() if v not in (None, [], {}, "")}


def _time_or_error(value: Any) -> tuple[str | None, str | None]:
    try:
        return normalize_time_string(value), None
    except ValueError:
        return None, "invalid_time"


# --------------------------------------------------------------------------
# Sections (one form each)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    schema: Callable[[dict[str, Any]], vol.Schema]
    values: Callable[[dict[str, Any]], dict[str, Any]]
    apply: Callable[[dict[str, Any], dict[str, Any]], dict[str, str]]


def _triggers_schema(options):
    return vol.Schema(
        {
            vol.Required(CONF_SENSORS): ENTITIES,
            vol.Required(CONF_SENSOR_TYPE): SENSOR_TYPE,
            vol.Optional(CONF_SENSOR_RESETS_TIMER): BOOLEAN,
            vol.Optional(CONF_HOLD_SENSORS): ENTITIES,
            vol.Optional(CONF_MAX_HOLD_TIME): _seconds(),
        }
    )


def _triggers_values(options):
    return _drop_empty(
        {
            CONF_SENSORS: options[CONF_SENSORS],
            CONF_SENSOR_TYPE: options[CONF_SENSOR_TYPE],
            CONF_HOLD_SENSORS: options[CONF_HOLD_SENSORS],
            CONF_MAX_HOLD_TIME: options[CONF_MAX_HOLD_TIME],
        }
    ) | {CONF_SENSOR_RESETS_TIMER: options[CONF_SENSOR_RESETS_TIMER]}


def _triggers_apply(options, user_input):
    options[CONF_SENSORS] = _list(user_input.get(CONF_SENSORS))
    options[CONF_SENSOR_TYPE] = user_input.get(CONF_SENSOR_TYPE, SENSOR_TYPE_EVENT)
    options[CONF_SENSOR_RESETS_TIMER] = bool(user_input.get(CONF_SENSOR_RESETS_TIMER, False))
    options[CONF_HOLD_SENSORS] = _list(user_input.get(CONF_HOLD_SENSORS))
    options[CONF_MAX_HOLD_TIME] = _int_or_none(user_input.get(CONF_MAX_HOLD_TIME))
    if not options[CONF_SENSORS]:
        return {CONF_SENSORS: "no_sensors"}
    return {}


def _entities_schema(options):
    return vol.Schema(
        {
            vol.Optional(CONF_CONTROL_ENTITIES): ENTITIES,
            vol.Optional(CONF_STATE_ENTITIES): ENTITIES,
            vol.Optional(CONF_TRIGGER_ON_ACTIVATE): ENTITIES,
            vol.Optional(CONF_TRIGGER_ON_DEACTIVATE): ENTITIES,
        }
    )


def _entities_values(options):
    return _drop_empty(
        {
            key: options[key]
            for key in (
                CONF_CONTROL_ENTITIES,
                CONF_STATE_ENTITIES,
                CONF_TRIGGER_ON_ACTIVATE,
                CONF_TRIGGER_ON_DEACTIVATE,
            )
        }
    )


def _entities_apply(options, user_input):
    for key in (
        CONF_CONTROL_ENTITIES,
        CONF_STATE_ENTITIES,
        CONF_TRIGGER_ON_ACTIVATE,
        CONF_TRIGGER_ON_DEACTIVATE,
    ):
        options[key] = _list(user_input.get(key))
    if not options[CONF_CONTROL_ENTITIES] and not options[CONF_TRIGGER_ON_ACTIVATE]:
        return {"base": "no_entities"}
    return {}


def _timer_schema(options):
    return vol.Schema(
        {
            vol.Required(CONF_DELAY): _seconds(),
            vol.Optional(CONF_STAY_MODE): BOOLEAN,
            vol.Optional(CONF_BACKOFF): BOOLEAN,
            vol.Optional(CONF_BACKOFF_FACTOR): BACKOFF_FACTOR,
            vol.Optional(CONF_BACKOFF_MAX): _seconds(),
        }
    )


def _timer_values(options):
    return {
        CONF_DELAY: options[CONF_DELAY],
        CONF_STAY_MODE: options[CONF_STAY_MODE],
        CONF_BACKOFF: options[CONF_BACKOFF],
        CONF_BACKOFF_FACTOR: options[CONF_BACKOFF_FACTOR],
        CONF_BACKOFF_MAX: options[CONF_BACKOFF_MAX],
    }


def _timer_apply(options, user_input):
    options[CONF_DELAY] = int(float(user_input.get(CONF_DELAY, DEFAULT_DELAY)))
    options[CONF_STAY_MODE] = bool(user_input.get(CONF_STAY_MODE, False))
    options[CONF_BACKOFF] = bool(user_input.get(CONF_BACKOFF, False))
    factor = user_input.get(CONF_BACKOFF_FACTOR)
    options[CONF_BACKOFF_FACTOR] = float(factor) if factor not in (None, "") else DEFAULT_BACKOFF_FACTOR
    backoff_max = user_input.get(CONF_BACKOFF_MAX)
    options[CONF_BACKOFF_MAX] = (
        int(float(backoff_max)) if backoff_max not in (None, "") else DEFAULT_BACKOFF_MAX
    )
    if options[CONF_BACKOFF_FACTOR] <= 0:
        return {CONF_BACKOFF_FACTOR: "invalid_backoff_factor"}
    return {}


def _service_data_schema(options):
    return vol.Schema(
        {
            vol.Optional(CONF_SERVICE_DATA): OBJECT,
            vol.Optional(CONF_SERVICE_DATA_OFF): OBJECT,
        }
    )


def _service_data_values(options):
    return _drop_empty(
        {
            CONF_SERVICE_DATA: options[CONF_SERVICE_DATA],
            CONF_SERVICE_DATA_OFF: options[CONF_SERVICE_DATA_OFF],
        }
    )


def _service_data_apply(options, user_input):
    errors = {}
    for key in (CONF_SERVICE_DATA, CONF_SERVICE_DATA_OFF):
        value = _dict_or_error(user_input.get(key))
        if value is None:
            errors[key] = "invalid_service_data"
        else:
            options[key] = value
    return errors


def _constraints_schema(options):
    return vol.Schema(
        {
            vol.Optional(CONF_START_TIME): TEXT,
            vol.Optional(CONF_END_TIME): TEXT,
        }
    )


def _constraints_values(options):
    return _drop_empty(
        {CONF_START_TIME: options[CONF_START_TIME], CONF_END_TIME: options[CONF_END_TIME]}
    )


def _constraints_apply(options, user_input):
    errors = {}
    for key in (CONF_START_TIME, CONF_END_TIME):
        value, error = _time_or_error(user_input.get(key))
        if error:
            errors[key] = error
        options[key] = value
    if not errors and bool(options[CONF_START_TIME]) != bool(options[CONF_END_TIME]):
        errors["base"] = "time_pair"
    return errors


def _night_schema(options):
    return vol.Schema(
        {
            vol.Optional(CONF_ENABLED): BOOLEAN,
            vol.Optional(CONF_START_TIME): TEXT,
            vol.Optional(CONF_END_TIME): TEXT,
            vol.Optional(CONF_DELAY): _seconds(),
            vol.Optional(CONF_SERVICE_DATA): OBJECT,
            vol.Optional(CONF_SERVICE_DATA_OFF): OBJECT,
        }
    )


def _night_values(options):
    night = options[CONF_NIGHT_MODE] or {}
    return _drop_empty(
        {
            CONF_START_TIME: night.get(CONF_START_TIME),
            CONF_END_TIME: night.get(CONF_END_TIME),
            CONF_DELAY: night.get(CONF_DELAY),
            CONF_SERVICE_DATA: night.get(CONF_SERVICE_DATA),
            CONF_SERVICE_DATA_OFF: night.get(CONF_SERVICE_DATA_OFF),
        }
    ) | {CONF_ENABLED: bool(night) and night.get(CONF_ENABLED, True)}


def _night_apply(options, user_input):
    errors = {}
    enabled = bool(user_input.get(CONF_ENABLED, False))
    night: dict[str, Any] = {CONF_ENABLED: enabled}
    for key in (CONF_START_TIME, CONF_END_TIME):
        value, error = _time_or_error(user_input.get(key))
        if error:
            errors[key] = error
        elif enabled and not value:
            errors[key] = "required_night_time"
        night[key] = value
    delay = user_input.get(CONF_DELAY)
    night[CONF_DELAY] = int(float(delay)) if delay not in (None, "") else None
    for key in (CONF_SERVICE_DATA, CONF_SERVICE_DATA_OFF):
        value = _dict_or_error(user_input.get(key))
        if value is None:
            errors[key] = "invalid_service_data"
        night[key] = value or {}
    has_values = any(night.get(k) for k in (CONF_START_TIME, CONF_END_TIME, CONF_DELAY))
    options[CONF_NIGHT_MODE] = night if (enabled or has_values) else None
    return errors


def _blocking_schema(options):
    return vol.Schema(
        {
            vol.Optional(CONF_OVERRIDES): ENTITIES,
            vol.Optional(CONF_DISABLE_BLOCK): BOOLEAN,
            vol.Optional(CONF_BLOCK_TIMEOUT): _seconds(),
            vol.Optional(CONF_GRACE_PERIOD): _seconds(),
        }
    )


def _blocking_values(options):
    return _drop_empty(
        {
            CONF_OVERRIDES: options[CONF_OVERRIDES],
            CONF_BLOCK_TIMEOUT: options[CONF_BLOCK_TIMEOUT],
            CONF_GRACE_PERIOD: options[CONF_GRACE_PERIOD],
        }
    ) | {CONF_DISABLE_BLOCK: options[CONF_DISABLE_BLOCK]}


def _blocking_apply(options, user_input):
    options[CONF_OVERRIDES] = _list(user_input.get(CONF_OVERRIDES))
    options[CONF_DISABLE_BLOCK] = bool(user_input.get(CONF_DISABLE_BLOCK, False))
    options[CONF_BLOCK_TIMEOUT] = _int_or_none(user_input.get(CONF_BLOCK_TIMEOUT))
    options[CONF_GRACE_PERIOD] = _int_or_none(user_input.get(CONF_GRACE_PERIOD))
    return {}


def _behaviours_schema(options):
    return vol.Schema({vol.Required(key): BEHAVIOUR for key in DEFAULT_BEHAVIOURS})


def _behaviours_values(options):
    return {key: options[CONF_BEHAVIOURS].get(key, default) for key, default in DEFAULT_BEHAVIOURS.items()}


def _behaviours_apply(options, user_input):
    behaviours = {}
    for key, default in DEFAULT_BEHAVIOURS.items():
        value = user_input.get(key, default)
        if value not in TRANSITION_BEHAVIOUR_OPTIONS:
            return {key: "invalid_behaviour"}
        behaviours[key] = value
    options[CONF_BEHAVIOURS] = behaviours
    return {}


def _advanced_schema(options):
    schema = {
        vol.Optional(CONF_STATE_ATTRIBUTES_IGNORE): _strings(COMMON_IGNORED_ATTRIBUTES),
        vol.Optional(CONF_IGNORED_EVENT_SOURCES): selector.TextSelector(
            selector.TextSelectorConfig(multiple=True)
        ),
        vol.Optional(CONF_STATE_STRINGS_ON): _strings([]),
        vol.Optional(CONF_STATE_STRINGS_OFF): _strings([]),
    }
    for key in STATE_STRING_KEYS:
        defaults = DEFAULT_STATES_ON if key.endswith("_on") else DEFAULT_STATES_OFF
        schema[vol.Optional(key)] = _strings(defaults)
    return vol.Schema(schema)


ADVANCED_KEYS = [
    CONF_STATE_ATTRIBUTES_IGNORE,
    CONF_IGNORED_EVENT_SOURCES,
    CONF_STATE_STRINGS_ON,
    CONF_STATE_STRINGS_OFF,
    *STATE_STRING_KEYS,
]


def _advanced_values(options):
    return _drop_empty({key: options[key] for key in ADVANCED_KEYS})


def _advanced_apply(options, user_input):
    errors = {}
    for key in ADVANCED_KEYS:
        options[key] = list(dict.fromkeys(_list(user_input.get(key))))
    for pattern in options[CONF_IGNORED_EVENT_SOURCES]:
        try:
            re.compile(pattern)
        except re.error:
            errors[CONF_IGNORED_EVENT_SOURCES] = "invalid_regex"
    return errors


SECTIONS: dict[str, Section] = {
    "triggers": Section(_triggers_schema, _triggers_values, _triggers_apply),
    "entities": Section(_entities_schema, _entities_values, _entities_apply),
    "timer": Section(_timer_schema, _timer_values, _timer_apply),
    "service_data": Section(_service_data_schema, _service_data_values, _service_data_apply),
    "constraints": Section(_constraints_schema, _constraints_values, _constraints_apply),
    "night_mode": Section(_night_schema, _night_values, _night_apply),
    "blocking": Section(_blocking_schema, _blocking_values, _blocking_apply),
    "behaviours": Section(_behaviours_schema, _behaviours_values, _behaviours_apply),
    "advanced": Section(_advanced_schema, _advanced_values, _advanced_apply),
}

# Which form shows a given validate_options() error.
ERROR_SECTIONS = {
    CONF_SENSORS: "triggers",
    CONF_CONTROL_ENTITIES: "entities",
    CONF_START_TIME: "constraints",
    CONF_END_TIME: "constraints",
    f"night_{CONF_START_TIME}": "night_mode",
    f"night_{CONF_END_TIME}": "night_mode",
    f"night_{CONF_SERVICE_DATA}": "night_mode",
    f"night_{CONF_SERVICE_DATA_OFF}": "night_mode",
    CONF_BACKOFF_FACTOR: "timer",
    CONF_BEHAVIOURS: "behaviours",
    CONF_SERVICE_DATA: "service_data",
    CONF_SERVICE_DATA_OFF: "service_data",
}


class _ControllerSteps:
    """Form steps shared by the config flow and the options flow."""

    _options: dict[str, Any]

    async def _async_show_menu(self) -> ConfigFlowResult:
        raise NotImplementedError

    def _show_section(
        self, name: str, values: dict[str, Any], errors: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        schema = SECTIONS[name].schema(self._options)
        return self.async_show_form(
            step_id=name,
            data_schema=self.add_suggested_values_to_schema(schema, values),
            errors=errors or {},
            last_step=False,
        )

    async def _async_section(self, name: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        section = SECTIONS[name]
        if user_input is None:
            return self._show_section(name, section.values(self._options))
        candidate = copy.deepcopy(self._options)
        errors = section.apply(candidate, user_input)
        if errors:
            return self._show_section(name, user_input, errors)
        self._options = candidate
        return await self._async_show_menu()

    def _invalid_section(self) -> ConfigFlowResult | None:
        """Show the first form with an error that prevents saving, if any."""
        errors = validate_options(self._options)
        if not errors:
            return None
        key = next(iter(errors))
        name = ERROR_SECTIONS.get(key, "triggers")
        field = key.removeprefix("night_") if name == "night_mode" else key
        if name == "entities" or field not in SECTIONS[name].schema(self._options).schema:
            field = "base"
        return self._show_section(name, SECTIONS[name].values(self._options), {field: errors[key]})

    async def async_step_triggers(self, user_input=None):
        return await self._async_section("triggers", user_input)

    async def async_step_entities(self, user_input=None):
        return await self._async_section("entities", user_input)

    async def async_step_timer(self, user_input=None):
        return await self._async_section("timer", user_input)

    async def async_step_service_data(self, user_input=None):
        return await self._async_section("service_data", user_input)

    async def async_step_constraints(self, user_input=None):
        return await self._async_section("constraints", user_input)

    async def async_step_night_mode(self, user_input=None):
        return await self._async_section("night_mode", user_input)

    async def async_step_blocking(self, user_input=None):
        return await self._async_section("blocking", user_input)

    async def async_step_behaviours(self, user_input=None):
        return await self._async_section("behaviours", user_input)

    async def async_step_advanced(self, user_input=None):
        return await self._async_section("advanced", user_input)


class EntityControllerConfigFlow(_ControllerSteps, ConfigFlow, domain=DOMAIN):
    """Create a new Entity Controller."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._options = default_options()
        self._title = ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EntityControllerOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the minimum needed to create a working controller."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._title = str(user_input.get(CONF_NAME, "")).strip()
            self._options[CONF_SENSORS] = _list(user_input.get(CONF_SENSORS))
            self._options[CONF_SENSOR_TYPE] = user_input.get(CONF_SENSOR_TYPE, SENSOR_TYPE_EVENT)
            self._options[CONF_CONTROL_ENTITIES] = _list(user_input.get(CONF_CONTROL_ENTITIES))
            self._options[CONF_DELAY] = int(float(user_input.get(CONF_DELAY, DEFAULT_DELAY)))
            if not self._title:
                errors[CONF_NAME] = "name_required"
            if not self._options[CONF_SENSORS]:
                errors[CONF_SENSORS] = "no_sensors"
            if not errors:
                return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): TEXT,
                vol.Required(CONF_SENSORS): ENTITIES,
                vol.Required(CONF_SENSOR_TYPE): SENSOR_TYPE,
                vol.Optional(CONF_CONTROL_ENTITIES): ENTITIES,
                vol.Required(CONF_DELAY): _seconds(),
            }
        )
        values = user_input or {
            CONF_SENSOR_TYPE: SENSOR_TYPE_EVENT,
            CONF_DELAY: DEFAULT_DELAY,
        }
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, values),
            errors=errors,
            last_step=False,
        )

    async def _async_show_menu(self) -> ConfigFlowResult:
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="menu", menu_options=[*SECTIONS, "finish"])

    async def async_step_finish(self, user_input=None) -> ConfigFlowResult:
        if result := self._invalid_section():
            return result
        return self.async_create_entry(title=self._title, data={}, options=self._options)

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import a controller from YAML."""
        key = import_data[CONF_YAML_KEY]
        await self.async_set_unique_id(f"yaml_{key}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=import_data["title"],
            data={CONF_YAML_KEY: key, CONF_ENTITY_ID: import_data[CONF_ENTITY_ID]},
            options=complete_options(import_data["options"]),
        )


class EntityControllerOptionsFlow(_ControllerSteps, OptionsFlow):
    """Edit an existing Entity Controller."""

    def __init__(self) -> None:
        self._options: dict[str, Any] | None = None

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if self._options is None:
            self._options = complete_options(dict(self.config_entry.options))
        return self.async_show_menu(step_id="init", menu_options=[*SECTIONS, "save"])

    async def _async_show_menu(self) -> ConfigFlowResult:
        return await self.async_step_init()

    async def async_step_save(self, user_input=None) -> ConfigFlowResult:
        if result := self._invalid_section():
            return result
        return self.async_create_entry(title="", data=self._options)
