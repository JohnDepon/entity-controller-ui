"""Generate custom_components/entity_controller/translations/en.json.

The config flow (create a controller) and the options flow (edit a
controller) share the same forms. Their texts are defined once here.

    python scripts/generate_translations.py
"""
from __future__ import annotations

import json
from pathlib import Path

TARGET = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "entity_controller"
    / "translations"
    / "en.json"
)

TIME_HELP = (
    "HH:MM:SS (e.g. 22:30:00), sunrise or sunset, optionally with an offset "
    "such as `sunset - 00:30:00` or `sunrise + 01:00:00`."
)

SECTIONS = {
    "triggers": {
        "title": "Sensors",
        "description": (
            "Sensors trigger the controller: when one of them turns on, the "
            "controlled entities are turned on."
        ),
        "data": {
            "sensors": "Trigger sensors",
            "sensor_type": "Sensor type",
            "sensor_resets_timer": "Restart the timer when the sensors turn off",
            "hold_sensors": "Hold sensors (keep on, never trigger)",
            "max_hold_time": "Maximum hold time",
        },
        "data_description": {
            "sensors": (
                "Motion sensors, door contacts, presence sensors, input booleans... "
                "Any entity whose state becomes `on` (see Advanced for other states)."
            ),
            "sensor_type": (
                "Event: the sensor only signals that something happened; the timer "
                "turns things off. Duration: the sensor stays on while there is "
                "motion/presence and the controller stays active until ALL sensors "
                "are off and the timer has expired."
            ),
            "sensor_resets_timer": (
                "Duration sensors only: when the last sensor turns off, start the "
                "full delay again instead of turning off as soon as the timer has expired."
            ),
            "hold_sensors": (
                "Optional. Typically presence (mmWave) sensors: while any of them is "
                "on the controlled entities stay on, but they never turn them on. "
                "Use this to trigger from a motion sensor and hold with a presence sensor."
            ),
            "max_hold_time": (
                "Optional, seconds. Protection against stuck sensors: a sensor that has "
                "reported 'on' for longer than this no longer keeps the entities on. "
                "Applies to hold sensors, and to trigger sensors with the Duration type. "
                "Choose more than the longest time you stay still in the room (e.g. "
                "7200 = 2 hours). Leave empty for no limit."
            ),
        },
    },
    "entities": {
        "title": "Controlled entities",
        "description": "Entities that are turned on and off by this controller.",
        "data": {
            "entities": "Controlled entities",
            "state_entities": "State entities",
            "trigger_on_activate": "Call turn_on on activation",
            "trigger_on_deactivate": "Call turn_on on deactivation",
        },
        "data_description": {
            "entities": "Lights, switches, fans, media players, groups... turned on and off with the service data configured for this controller.",
            "state_entities": (
                "Optional. Entities observed to decide whether the controlled "
                "entities are on. Leave empty to observe the controlled entities "
                "themselves (recommended). Needed for entities without a usable "
                "state, such as scenes or scripts."
            ),
            "trigger_on_activate": "Optional. Entities (usually scripts or scenes) on which only turn_on is called when the controller activates. Their state is not observed.",
            "trigger_on_deactivate": "Optional. Entities (usually scripts) on which turn_on is called when the controller deactivates.",
        },
    },
    "delayed": {
        "title": "Delayed entities",
        "description": (
            "Entities, e.g. a bathroom fan, that are turned on only when the "
            "controller stays active for a while, and then keep running for a "
            "minimum time even if the controlled entities turn off meanwhile."
        ),
        "data": {
            "delayed_entities": "Delayed entities",
            "delayed_after": "Turn on after",
            "delayed_min_on": "Keep on for at least",
        },
        "data_description": {
            "delayed_entities": "Turned on with turn_on and off with turn_off. Entities that are already on at that moment are left alone.",
            "delayed_after": "Seconds the controller must stay active (someone stays in the room). If it goes idle earlier, they are not turned on.",
            "delayed_min_on": "Seconds they run at least, even if the controller goes idle meanwhile. Afterwards they stay on for as long as the controller stays active.",
        },
    },
    "timer": {
        "title": "Timer",
        "description": "How long the controlled entities stay on.",
        "data": {
            "delay": "Delay",
            "stay_mode": "Stay mode",
            "backoff": "Exponential backoff",
            "backoff_factor": "Backoff factor",
            "backoff_max": "Maximum delay with backoff",
        },
        "data_description": {
            "delay": "Seconds the entities stay on after the last trigger (default 180).",
            "stay_mode": "After being triggered, leave the entities on until they are turned off manually (state active_stay_on). Same setting as the Stay mode switch of the controller's device.",
            "backoff": "Every new trigger while active multiplies the delay by the backoff factor.",
            "backoff_factor": "Multiplier applied to the delay on every re-trigger (default 1.1).",
            "backoff_max": "The delay never grows beyond this many seconds (default 300).",
        },
    },
    "service_data": {
        "title": "Service data",
        "description": (
            "Extra data passed to the turn_on and turn_off service calls, e.g. "
            "`brightness_pct: 50` or `transition: 2`. All controlled entities must "
            "support the given keys. Values can be templates that depend on other "
            "entities, e.g. `{template_example}`; they are evaluated each time the "
            "entities are switched."
        ),
        "data": {
            "service_data": "turn_on service data",
            "service_data_off": "turn_off service data",
        },
        "data_description": {
            "service_data": "Also passed to the 'Call turn_on on activation' entities (use `variables:` for scripts).",
            "service_data_off": "Also passed to the 'Call turn_on on deactivation' entities.",
        },
    },
    "constraints": {
        "title": "Active hours",
        "description": (
            "Optionally restrict the controller to a time window. Outside the "
            "window it is `constrained` and ignores the sensors. Set both times or none."
        ),
        "data": {"start_time": "Start time", "end_time": "End time"},
        "data_description": {"start_time": TIME_HELP, "end_time": TIME_HELP},
    },
    "night_mode": {
        "title": "Night mode",
        "description": "Use a different delay and service data during the night, e.g. a dimmer light for a shorter time.",
        "data": {
            "enabled": "Enable night mode",
            "start_time": "Night start",
            "end_time": "Night end",
            "delay": "Night delay",
            "service_data": "Night turn_on service data",
            "service_data_off": "Night turn_off service data",
        },
        "data_description": {
            "enabled": "The settings below are kept when night mode is disabled.",
            "start_time": TIME_HELP,
            "end_time": TIME_HELP,
            "delay": "Seconds. Leave empty to use the normal delay.",
            "service_data": "Leave empty to use the normal turn_on service data.",
            "service_data_off": "Leave empty to use the normal turn_off service data.",
        },
    },
    "blocking": {
        "title": "Overrides & blocking",
        "description": (
            "When a sensor triggers while the controlled entities are already on "
            "(turned on by someone else), the controller is `blocked` and leaves "
            "them alone until they are turned off."
        ),
        "data": {
            "overrides": "Override entities",
            "disable_block": "Disable blocking",
            "block_timeout": "Block timeout",
            "grace_period": "Grace period",
        },
        "data_description": {
            "overrides": "While any of these entities is on, the controller is `overridden` and does nothing (e.g. an input_boolean or a TV).",
            "disable_block": "Never block: take over entities that are already on and start the timer (it will turn them off).",
            "block_timeout": "Optional, seconds. Leave the blocked state after this time when a sensor triggers again, so manually switched lights are eventually turned off.",
            "grace_period": (
                "Optional, seconds. Ignore state changes of the controlled entities "
                "for this long after the controller switched them. Only needed for "
                "integrations whose state updates arrive late or without context "
                "(e.g. cloud integrations), which otherwise make the controller block itself."
            ),
        },
    },
    "behaviours": {
        "title": "Transition behaviours",
        "description": "What to do with the controlled entities when the controller enters or leaves a state.",
        "data": {
            "on_enter_idle": "Entering idle",
            "on_exit_idle": "Leaving idle",
            "on_enter_active": "Entering active",
            "on_exit_active": "Leaving active",
            "on_enter_overridden": "Entering overridden",
            "on_exit_overridden": "Leaving overridden",
            "on_enter_constrained": "Entering constrained (end of active hours)",
            "on_exit_constrained": "Leaving constrained (start of active hours)",
            "on_enter_blocked": "Entering blocked",
            "on_exit_blocked": "Leaving blocked",
        },
        "data_description": {
            "on_enter_idle": "Default: turn off.",
            "on_enter_active": "Default: turn on.",
            "on_enter_constrained": "Use 'Turn off' to switch off lights left on when the active hours end.",
        },
    },
    "advanced": {
        "title": "Advanced",
        "description": (
            "By default `on`, `playing`, `home` and `True` count as on and `off`, "
            "`idle`, `paused`, `away` and `False` count as off. Leave a list empty "
            "to use these defaults."
        ),
        "data": {
            "state_attributes_ignore": "Ignored attribute changes",
            "ignored_event_sources": "Ignored event sources",
            "state_strings_on": "Additional 'on' states (all entities)",
            "state_strings_off": "Additional 'off' states (all entities)",
            "sensor_states_on": "Sensor 'on' states",
            "sensor_states_off": "Sensor 'off' states",
            "control_states_on": "Controlled entity 'on' states",
            "control_states_off": "Controlled entity 'off' states",
            "state_states_on": "State entity 'on' states",
            "state_states_off": "State entity 'off' states",
            "override_states_on": "Override 'on' states",
            "override_states_off": "Override 'off' states",
        },
        "data_description": {
            "state_attributes_ignore": (
                "Attribute-only changes of the controlled entities count as manual "
                "control (and block the controller) unless the attribute is listed "
                "here, e.g. brightness/color_temp when using adaptive lighting."
            ),
            "ignored_event_sources": "Regular expressions matched against the context id of state changes to ignore (see debug log), e.g. `adapt_lgt_.*`.",
            "state_strings_on": "Added to every 'on' list below.",
            "state_strings_off": "Added to every 'off' list below.",
            "sensor_states_on": "Replaces the default 'on' states for sensors.",
            "sensor_states_off": "Replaces the default 'off' states for sensors.",
            "control_states_on": "Replaces the default 'on' states for controlled entities.",
            "control_states_off": "Replaces the default 'off' states for controlled entities.",
            "state_states_on": "Replaces the default 'on' states for state entities.",
            "state_states_off": "Replaces the default 'off' states for state entities.",
            "override_states_on": "Replaces the default 'on' states for override entities.",
            "override_states_off": "Replaces the default 'off' states for override entities.",
        },
    },
}

MENU_LABELS = {name: section["title"] for name, section in SECTIONS.items()}

ERRORS = {
    "name_required": "Enter a name.",
    "no_sensors": "Select at least one trigger sensor.",
    "no_entities": "Select at least one controlled entity or one entity to call turn_on on activation.",
    "invalid_time": "Invalid time. Use HH:MM:SS, sunrise, sunset or e.g. sunset - 00:30:00.",
    "time_pair": "Set both the start time and the end time, or neither.",
    "required_night_time": "Night mode needs a start time and an end time.",
    "invalid_backoff_factor": "The backoff factor must be greater than 0.",
    "invalid_behaviour": "Choose turn on, turn off or do nothing.",
    "invalid_service_data": "Service data must be a mapping (key: value pairs).",
    "invalid_regex": "One of the patterns is not a valid regular expression.",
}


def build() -> dict:
    steps = {name: dict(section) for name, section in SECTIONS.items()}
    config_steps = {
        "user": {
            "title": "New Entity Controller",
            "description": (
                "Turn entities on when a sensor triggers and off again after a delay. "
                "All other options can be set on the next page, or later with "
                "Configure on the Entity Controller integration page."
            ),
            "data": {
                "name": "Name",
                "sensors": SECTIONS["triggers"]["data"]["sensors"],
                "sensor_type": SECTIONS["triggers"]["data"]["sensor_type"],
                "entities": SECTIONS["entities"]["data"]["entities"],
                "delay": SECTIONS["timer"]["data"]["delay"],
            },
            "data_description": {
                "name": "Also used for the entity id, e.g. entity_controller.hallway_motion.",
                "sensors": SECTIONS["triggers"]["data_description"]["sensors"],
                "sensor_type": SECTIONS["triggers"]["data_description"]["sensor_type"],
                "entities": SECTIONS["entities"]["data_description"]["entities"],
                "delay": SECTIONS["timer"]["data_description"]["delay"],
            },
        },
        "menu": {
            "title": "Configure the new controller",
            "description": "Optionally adjust more settings, then create the controller.",
            "menu_options": {**MENU_LABELS, "finish": "Create controller"},
        },
        **steps,
    }
    options_steps = {
        "init": {
            "title": "Configure controller",
            "description": "Choose what to change. Changes are applied when you choose Save.",
            "menu_options": {**MENU_LABELS, "save": "Save"},
        },
        **steps,
    }
    return {
        "config": {
            # Label of the button on the integration page (instead of "Add service").
            "initiate_flow": {"user": "Add controller"},
            "step": config_steps,
            "error": ERRORS,
            "abort": {"already_configured": "This YAML controller has already been imported."},
        },
        "options": {"step": options_steps, "error": ERRORS},
        "selector": {
            "sensor_type": {
                "options": {
                    "event": "Event (momentary trigger, timer decides)",
                    "duration": "Duration (on while motion/presence lasts)",
                }
            },
            "behaviour": {
                "options": {"on": "Turn on", "off": "Turn off", "ignore": "Do nothing"}
            },
        },
        # States of the entity_controller.* entities, as shown in the UI.
        "entity_component": {
            "_": {
                "name": "Entity controller",
                "state": {
                    "pending": "Starting",
                    "idle": "Idle",
                    "active": "Active",
                    "active_timer": "Active (timer)",
                    "active_stay_on": "Active (stay on)",
                    "blocked": "Blocked",
                    "overridden": "Overridden",
                    "constrained": "Outside active hours",
                },
                "state_attributes": {
                    "delayed_entities": {"name": "Delayed entities"},
                    "delayed_until": {"name": "Delayed until"},
                    "delayed_status": {
                        "name": "Delayed status",
                        "state": {
                            "off": "Off",
                            "waiting": "Waiting (someone present)",
                            "running": "On (minimum time)",
                            "running_until_idle": "On (until the room is empty)",
                        },
                    },
                },
            }
        },
        "entity": {
            "button": {
                "activate": {"name": "Activate"},
                "clear_block": {"name": "Clear block"},
                "enable_block": {"name": "Enable block"},
            },
            "switch": {"stay_mode": {"name": "Stay mode"}},
        },
        "exceptions": {
            "starting": {
                "message": "The controller is still starting up, try again in a moment."
            },
            "activate_not_possible": {
                "message": "The controller cannot be activated while it is {state}."
            },
            "not_blocked": {"message": "The controller is not blocked (it is {state})."},
            "not_active_timer": {
                "message": (
                    "Blocking is only possible while the timer is running and the "
                    "controlled entities are on (the controller is {state})."
                )
            },
        },
        "issues": {
            "deprecated_yaml": {
                "title": "Entity Controller YAML configuration was imported",
                "description": (
                    "The Entity Controller YAML configuration was imported "
                    "(controllers: {controllers}). Controllers are now managed under "
                    "Settings > Devices & services > Integrations > Entity Controller; "
                    "changes made in YAML are no longer applied.\n\nRemove the "
                    "`entity_controller:` section from your YAML configuration and "
                    "restart Home Assistant to fix this issue."
                ),
            },
            "yaml_import_failed": {
                "title": "Some Entity Controller YAML controllers could not be imported",
                "description": (
                    "These YAML controllers could not be imported: {controllers}. The "
                    "reason is in the Home Assistant log. Fix them in YAML and restart, "
                    "or add them with Add controller on the Entity Controller "
                    "integration page."
                ),
            },
        },
        "services": {
            "activate": {
                "name": "Activate",
                "description": "Activates a controller: turns on its entities and starts the timer. Also clears the blocked state.",
            },
            "clear_block": {
                "name": "Clear block",
                "description": "Clears the blocked state of a controller, as if its block timeout expired.",
            },
            "enable_block": {
                "name": "Enable block",
                "description": "Puts an active controller into the blocked state, so it will not turn its entities off.",
            },
            "enable_stay_mode": {
                "name": "Enable stay mode",
                "description": "Turns on stay mode (same as the controller's Stay mode switch): from the next activation, entities stay on until turned off manually.",
            },
            "disable_stay_mode": {
                "name": "Disable stay mode",
                "description": "Turns off stay mode (same as the controller's Stay mode switch): from the next activation, the timer turns the entities off again.",
            },
            "set_night_mode": {
                "name": "Set night mode",
                "description": (
                    "Changes the night mode start and end times until the controller is "
                    "reloaded. Does nothing if night mode is not enabled. Without any "
                    "time, both are set to midnight, which disables night mode."
                ),
                "fields": {
                    "start_time": {
                        "name": "Start time",
                        "description": "New night start: a time, sunrise/sunset with offset, `now`, or `constraint` (the start of the active hours).",
                    },
                    "end_time": {
                        "name": "End time",
                        "description": "New night end: a time, sunrise/sunset with offset, `now`, or `constraint` (the end of the active hours).",
                    },
                },
            },
        },
    }


if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {TARGET}")
