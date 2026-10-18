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
"""Canonical controller options.

Every controller, whether it was created in the UI or imported from YAML, is
stored as one config entry whose ``options`` follow the canonical layout built
by :func:`default_options`. The keys are the same as the documented YAML keys
(always using the plural form for lists) so the documentation keeps applying.
"""

import copy
import re
from typing import Any

from .const import (
    CONF_BACKOFF,
    CONF_BACKOFF_FACTOR,
    CONF_BACKOFF_MAX,
    CONF_BEHAVIOURS,
    CONF_BLOCK_TIMEOUT,
    CONF_CONTROL_ENTITIES,
    CONF_CONTROL_ENTITY,
    CONF_DAY_LENGTH,
    CONF_DELAY,
    CONF_DELAYED_AFTER,
    CONF_DELAYED_ENTITIES,
    CONF_DELAYED_MIN_ON,
    CONF_DISABLE_BLOCK,
    CONF_ENABLED,
    CONF_END_TIME,
    CONF_FRIENDLY_NAME,
    CONF_GRACE_PERIOD,
    CONF_HOLD_SENSORS,
    CONF_HOLD_MAX_SECONDS,
    CONF_IGNORED_EVENT_SOURCES,
    CONF_MAX_HOLD_TIME,
    CONF_NIGHT_MODE,
    CONF_OVERRIDE,
    CONF_OVERRIDES,
    CONF_SENSOR,
    CONF_SENSOR_RESETS_TIMER,
    CONF_SENSOR_TYPE,
    CONF_SENSOR_TYPE_DURATION,
    CONF_SENSORS,
    CONF_SERVICE_DATA,
    CONF_SERVICE_DATA_OFF,
    CONF_SERVICE_DATA_ON,
    CONF_START_TIME,
    CONF_STATE_ATTRIBUTES_IGNORE,
    CONF_STATE_ENTITIES,
    CONF_STATE_ENTITY,
    CONF_STATE_STRINGS_OFF,
    CONF_STATE_STRINGS_ON,
    CONF_STAY_MODE,
    CONF_TRIGGER_ON_ACTIVATE,
    CONF_TRIGGER_ON_DEACTIVATE,
    DEFAULT_BACKOFF_FACTOR,
    DEFAULT_BACKOFF_MAX,
    DEFAULT_BEHAVIOURS,
    DEFAULT_DELAY,
    SENSOR_TYPE_DURATION,
    SENSOR_TYPE_EVENT,
    STATE_STRING_KEYS,
    TRANSITION_BEHAVIOUR_OPTIONS,
)

# Keys that only existed for debugging/diagram drawing in old versions. They
# are accepted in YAML so old configurations import cleanly, but are dropped.
OBSOLETE_YAML_KEYS = {"draw", "image_prefix", "image_path", "name"}

ENTITY_LIST_KEYS = [
    CONF_SENSORS,
    CONF_HOLD_SENSORS,
    CONF_CONTROL_ENTITIES,
    CONF_STATE_ENTITIES,
    CONF_TRIGGER_ON_ACTIVATE,
    CONF_TRIGGER_ON_DEACTIVATE,
    CONF_OVERRIDES,
]

NIGHT_MODE_KEYS = [
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_DELAY,
    CONF_SERVICE_DATA,
    CONF_SERVICE_DATA_OFF,
]

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?$")
_DATETIME_RE = re.compile(r"^\d+-\d+-\d+\s+\d+:\d+:\d+$")
_SUN_RE = re.compile(
    r"^(sunrise|sunset)(?:\s*([+-])\s*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?$"
)
# Debugging syntax supported by the time parser, e.g. "now + 30 (5)"
_NOW_RE = re.compile(r"^now\s*[+-]\s*\d+\s*(\(\d+\))?$")


def default_options() -> dict[str, Any]:
    """Return a fresh copy of the default controller options."""
    return {
        # Triggers
        CONF_SENSORS: [],
        CONF_SENSOR_TYPE: SENSOR_TYPE_EVENT,
        CONF_SENSOR_RESETS_TIMER: False,
        CONF_HOLD_SENSORS: [],
        CONF_MAX_HOLD_TIME: None,
        # Controlled entities
        CONF_CONTROL_ENTITIES: [],
        CONF_STATE_ENTITIES: [],
        CONF_TRIGGER_ON_ACTIVATE: [],
        CONF_TRIGGER_ON_DEACTIVATE: [],
        # Delayed entities (e.g. a bathroom fan)
        CONF_DELAYED_ENTITIES: [],
        CONF_DELAYED_AFTER: 0,
        CONF_DELAYED_MIN_ON: 0,
        # Timer
        CONF_DELAY: DEFAULT_DELAY,
        CONF_STAY_MODE: False,
        CONF_BACKOFF: False,
        CONF_BACKOFF_FACTOR: DEFAULT_BACKOFF_FACTOR,
        CONF_BACKOFF_MAX: DEFAULT_BACKOFF_MAX,
        # Service data
        CONF_SERVICE_DATA: {},
        CONF_SERVICE_DATA_OFF: {},
        # Time constraints
        CONF_START_TIME: None,
        CONF_END_TIME: None,
        # Night mode (None = disabled)
        CONF_NIGHT_MODE: None,
        # Overrides and blocking
        CONF_OVERRIDES: [],
        CONF_DISABLE_BLOCK: False,
        CONF_BLOCK_TIMEOUT: None,
        CONF_GRACE_PERIOD: None,
        # Transition behaviours
        CONF_BEHAVIOURS: dict(DEFAULT_BEHAVIOURS),
        # Advanced
        CONF_STATE_ATTRIBUTES_IGNORE: [],
        CONF_IGNORED_EVENT_SOURCES: [],
        CONF_STATE_STRINGS_ON: [],
        CONF_STATE_STRINGS_OFF: [],
        **{key: [] for key in STATE_STRING_KEYS},
        CONF_DAY_LENGTH: None,
    }


def complete_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """Fill in defaults for any key missing from stored options.

    Keeps controllers created by older versions of this integration working
    when new options are added.
    """
    result = default_options()
    for key, value in (options or {}).items():
        if key == CONF_BEHAVIOURS and isinstance(value, dict):
            result[CONF_BEHAVIOURS].update(value)
        else:
            result[key] = copy.deepcopy(value)
    return result


# ---------------------------------------------------------------------------
# Time strings
# ---------------------------------------------------------------------------


def normalize_time_string(value: Any) -> str | None:
    """Validate a time constraint string and return its canonical form.

    Accepted formats (same as the YAML documentation):
      * ``HH:MM:SS`` (``HH:MM`` is accepted and padded with ``:00``)
      * ``sunrise`` / ``sunset``, optionally ``sunset - 00:30:00``
      * ``YYYY-MM-DD HH:MM:SS``
      * ``now + N`` debugging syntax

    Returns None for an empty value and raises ValueError when invalid.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"invalid time: {value}")
    if isinstance(value, int):
        # Unquoted YAML 1.1 times such as 22:00:00 are parsed as base-60
        # integers (seconds since midnight). Convert them back.
        if not 0 <= value < 86400:
            raise ValueError(f"invalid time: {value}")
        return f"{value // 3600:02d}:{(value % 3600) // 60:02d}:{value % 60:02d}"
    text = " ".join(str(value).strip().split())
    if not text:
        return None
    lowered = text.lower()

    if match := _TIME_RE.match(lowered):
        hour, minute, second = (int(match.group(i) or 0) for i in (1, 2, 3))
        if hour > 23 or minute > 59 or second > 59:
            raise ValueError(f"invalid time: {value}")
        return f"{hour:02d}:{minute:02d}:{second:02d}"

    if match := _SUN_RE.match(lowered):
        event, sign = match.group(1), match.group(2)
        if sign is None:
            return event
        hours, minutes, seconds = (int(match.group(i) or 0) for i in (3, 4, 5))
        if minutes > 59 or seconds > 59:
            raise ValueError(f"invalid time: {value}")
        return f"{event} {sign} {hours:02d}:{minutes:02d}:{seconds:02d}"

    if _DATETIME_RE.match(lowered) or _NOW_RE.match(lowered):
        return lowered

    raise ValueError(f"invalid time: {value}")


# ---------------------------------------------------------------------------
# Validation shared by the UI flows and the YAML import
# ---------------------------------------------------------------------------


def validate_options(options: dict[str, Any]) -> dict[str, str]:
    """Return a mapping of option key -> translation key of the error."""
    errors: dict[str, str] = {}

    if not options.get(CONF_SENSORS):
        errors[CONF_SENSORS] = "no_sensors"
    if not options.get(CONF_CONTROL_ENTITIES) and not options.get(
        CONF_TRIGGER_ON_ACTIVATE
    ):
        errors[CONF_CONTROL_ENTITIES] = "no_entities"

    start, end = options.get(CONF_START_TIME), options.get(CONF_END_TIME)
    for key, value in ((CONF_START_TIME, start), (CONF_END_TIME, end)):
        try:
            normalize_time_string(value)
        except ValueError:
            errors[key] = "invalid_time"
    if bool(start) != bool(end) and not errors.get(CONF_START_TIME) and not errors.get(
        CONF_END_TIME
    ):
        errors[CONF_START_TIME if not start else CONF_END_TIME] = "time_pair"

    night = options.get(CONF_NIGHT_MODE)
    if night and night.get(CONF_ENABLED, True):
        for key in (CONF_START_TIME, CONF_END_TIME):
            try:
                if not normalize_time_string(night.get(key)):
                    errors[f"night_{key}"] = "required_night_time"
            except ValueError:
                errors[f"night_{key}"] = "invalid_time"

    if (options.get(CONF_BACKOFF_FACTOR) or 0) <= 0:
        errors[CONF_BACKOFF_FACTOR] = "invalid_backoff_factor"

    for key, value in options.get(CONF_BEHAVIOURS, {}).items():
        if value not in TRANSITION_BEHAVIOUR_OPTIONS:
            errors[CONF_BEHAVIOURS] = "invalid_behaviour"

    for key in (CONF_SERVICE_DATA, CONF_SERVICE_DATA_OFF):
        if not isinstance(options.get(key) or {}, dict):
            errors[key] = "invalid_service_data"
    if night:
        for key in (CONF_SERVICE_DATA, CONF_SERVICE_DATA_OFF):
            if not isinstance(night.get(key) or {}, dict):
                errors[f"night_{key}"] = "invalid_service_data"

    return errors


# ---------------------------------------------------------------------------
# YAML (legacy) import
# ---------------------------------------------------------------------------


def _as_list(value: Any) -> list[str]:
    """Return a list of strings for a YAML value that may be a str or a list."""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if item is not None and str(item).strip()]
    return [str(value).strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "enable", "enabled")
    return bool(value)


def _as_number(value: Any, cast, minimum: float | None = None):
    if value is None or value == "":
        return None
    result = cast(float(value)) if cast is int else cast(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{value} is below {minimum}")
    return result


def _as_service_data(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("service data must be a mapping")
    return copy.deepcopy(dict(value))


def _as_behaviour(value: Any) -> str:
    # Unquoted on/off in YAML is parsed as a boolean.
    if value is True:
        return "on"
    if value is False:
        return "off"
    return str(value).strip().lower()


def legacy_to_options(key: str, raw: dict[str, Any] | None) -> tuple[str, dict[str, Any], list[str]]:
    """Convert one legacy YAML controller definition to canonical options.

    Returns ``(title, options, warnings)``. Raises ValueError for definitions
    that cannot be converted.
    """
    raw = dict(raw or {})
    warnings: list[str] = []
    options = default_options()

    def take(*names: str) -> list[str]:
        values: list[str] = []
        for name in names:
            values.extend(_as_list(raw.pop(name, None)))
        return _dedupe(values)

    title = str(raw.pop(CONF_FRIENDLY_NAME, None) or key)

    options[CONF_SENSORS] = take(CONF_SENSOR, CONF_SENSORS)
    options[CONF_HOLD_SENSORS] = take(CONF_HOLD_SENSORS)
    options[CONF_CONTROL_ENTITIES] = take(CONF_CONTROL_ENTITY, CONF_CONTROL_ENTITIES)
    # The documentation shows `state_entity`, the code only read `state_entities`.
    options[CONF_STATE_ENTITIES] = take(CONF_STATE_ENTITIES, CONF_STATE_ENTITY)
    options[CONF_TRIGGER_ON_ACTIVATE] = take(CONF_TRIGGER_ON_ACTIVATE)
    options[CONF_TRIGGER_ON_DEACTIVATE] = take(CONF_TRIGGER_ON_DEACTIVATE)
    options[CONF_OVERRIDES] = take(CONF_OVERRIDE, CONF_OVERRIDES)

    if _as_bool(raw.pop(CONF_SENSOR_TYPE_DURATION, False)):
        options[CONF_SENSOR_TYPE] = SENSOR_TYPE_DURATION
    if (sensor_type := raw.pop(CONF_SENSOR_TYPE, None)) is not None:
        sensor_type = str(sensor_type).strip().lower()
        if sensor_type not in (SENSOR_TYPE_EVENT, SENSOR_TYPE_DURATION):
            raise ValueError(f"sensor_type must be 'event' or 'duration', got '{sensor_type}'")
        options[CONF_SENSOR_TYPE] = sensor_type

    for name in (CONF_SENSOR_RESETS_TIMER, CONF_STAY_MODE, CONF_BACKOFF, CONF_DISABLE_BLOCK):
        if name in raw:
            options[name] = _as_bool(raw.pop(name))

    if (delay := _as_number(raw.pop(CONF_DELAY, None), int, 0)) is not None:
        options[CONF_DELAY] = delay
    if (factor := _as_number(raw.pop(CONF_BACKOFF_FACTOR, None), float, 0)) is not None:
        options[CONF_BACKOFF_FACTOR] = factor
    if (bmax := _as_number(raw.pop(CONF_BACKOFF_MAX, None), int, 0)) is not None:
        options[CONF_BACKOFF_MAX] = bmax
    options[CONF_BLOCK_TIMEOUT] = _as_number(raw.pop(CONF_BLOCK_TIMEOUT, None), int, 0)
    options[CONF_GRACE_PERIOD] = _as_number(raw.pop(CONF_GRACE_PERIOD, None), int, 0)
    max_hold = raw.pop(CONF_MAX_HOLD_TIME, None)
    alias = raw.pop(CONF_HOLD_MAX_SECONDS, None)
    options[CONF_MAX_HOLD_TIME] = (
        _as_number(max_hold if max_hold is not None else alias, int, 0) or None
    )
    options[CONF_DAY_LENGTH] = _as_number(raw.pop(CONF_DAY_LENGTH, None), int, 1)

    options[CONF_SERVICE_DATA] = _as_service_data(raw.pop(CONF_SERVICE_DATA, None))
    if (on_data := raw.pop(CONF_SERVICE_DATA_ON, None)) is not None:
        # Documented, but never implemented by the original code: merge it into
        # the turn_on service data, which is what the documentation implies.
        options[CONF_SERVICE_DATA].update(_as_service_data(on_data))
        warnings.append("'service_data_on' was merged into 'service_data'")
    options[CONF_SERVICE_DATA_OFF] = _as_service_data(raw.pop(CONF_SERVICE_DATA_OFF, None))

    options[CONF_START_TIME] = normalize_time_string(raw.pop(CONF_START_TIME, None))
    options[CONF_END_TIME] = normalize_time_string(raw.pop(CONF_END_TIME, None))

    night = raw.pop(CONF_NIGHT_MODE, None)
    if night:
        if not isinstance(night, dict):
            raise ValueError("night_mode must be a mapping")
        night = dict(night)
        options[CONF_NIGHT_MODE] = {
            CONF_ENABLED: True,
            CONF_START_TIME: normalize_time_string(night.pop(CONF_START_TIME, None)),
            CONF_END_TIME: normalize_time_string(night.pop(CONF_END_TIME, None)),
            CONF_DELAY: _as_number(night.pop(CONF_DELAY, None), int, 0),
            CONF_SERVICE_DATA: _as_service_data(night.pop(CONF_SERVICE_DATA, None)),
            CONF_SERVICE_DATA_OFF: _as_service_data(night.pop(CONF_SERVICE_DATA_OFF, None)),
        }
        if (on_data := night.pop(CONF_SERVICE_DATA_ON, None)) is not None:
            options[CONF_NIGHT_MODE][CONF_SERVICE_DATA].update(_as_service_data(on_data))
        for unknown in night:
            warnings.append(f"unknown night_mode option '{unknown}' was ignored")

    behaviours = raw.pop(CONF_BEHAVIOURS, None) or {}
    if not isinstance(behaviours, dict):
        raise ValueError("behaviours must be a mapping")
    for name, value in behaviours.items():
        if name not in DEFAULT_BEHAVIOURS:
            warnings.append(f"unknown behaviour '{name}' was ignored")
            continue
        value = _as_behaviour(value)
        if value not in TRANSITION_BEHAVIOUR_OPTIONS:
            raise ValueError(f"behaviour {name} must be one of on/off/ignore, got '{value}'")
        options[CONF_BEHAVIOURS][name] = value

    for name in (
        CONF_STATE_ATTRIBUTES_IGNORE,
        CONF_IGNORED_EVENT_SOURCES,
        CONF_STATE_STRINGS_ON,
        CONF_STATE_STRINGS_OFF,
        *STATE_STRING_KEYS,
    ):
        options[name] = _dedupe(_as_list(raw.pop(name, None)))

    for name in list(raw):
        if name in OBSOLETE_YAML_KEYS:
            raw.pop(name)
        else:
            warnings.append(f"unknown option '{name}' was ignored")

    return title, options, warnings
