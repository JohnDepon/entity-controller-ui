[![License](https://img.shields.io/badge/license-GPLv3-blue.svg?style=flat-square)](COPYING)

# Entity Controller with UI

Entity Controller (EC) implements "when this, then that, for x amount of
time" with a finite state machine that does not interfere with the rest of
your home automation. The classic use case is a motion-activated light that
turns off after a delay, but any entity can be used as a trigger or as
controlled entity.

This is a fork of [danobot/entity-controller](https://github.com/danobot/entity-controller)
(v9.7.6) by Daniel Mason. Compared to the original it:

* is a regular integration, managed **entirely from its page under
  Settings → Devices & services → Integrations** — every option, no YAML, no
  restart;
* imports your existing `entity_controller:` YAML once (same entity ids);
* fixes the bug where **lights turned off while a presence/motion sensor still
  reported presence** when several duration sensors were used, plus a series of
  other bugs, including fixes collected from other forks (see [CHANGELOG.md](CHANGELOG.md));
* adds *hold sensors* (e.g. mmWave presence sensors that keep the light on but
  never switch it on).

---

## Installation with HACS

Requires Home Assistant 2025.1 or newer and [HACS](https://hacs.xyz/).

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JohnDepon&repository=entity-controller-ui&category=integration)

The button above does steps 2 and 3 for you. To do it by hand:

1. **Remove the original Entity Controller first**, if you have it: in HACS
   open *Entity Controller* (by danobot) → ⋮ → *Remove*. Both use the same
   folder (`custom_components/entity_controller`). Your `entity_controller:`
   YAML is kept and imported later.
2. **Add this repository to HACS:** HACS → ⋮ (top right) → *Custom
   repositories* → Repository `https://github.com/JohnDepon/entity-controller-ui`,
   Type *Integration* → *Add*.
3. **Download it:** search HACS for **Entity Controller with UI**, open it,
   check that it shows `JohnDepon/entity-controller-ui`, then *Download* (the
   latest version is preselected).
4. **Restart Home Assistant:** Settings → System → ⏻ (top right) → *Restart
   Home Assistant*.
5. **Add your first controller:** Settings → Devices & services → *Add
   integration* → search **Entity Controller with UI**. Further controllers are
   added with **Add controller** on the integration page. If you had
   `entity_controller:` YAML, those controllers are already imported and
   listed there (see [Migrating](#migrating-from-the-original-entity-controller--yaml)).

**Updates:** HACS shows new versions under Settings → Updates; install the
update, then restart Home Assistant. The [release notes](https://github.com/JohnDepon/entity-controller-ui/releases)
list the changes.

Installing without HACS (copying the files, or from your own git server) is
described in [docs/INSTALL_AND_PUBLISH.md](docs/INSTALL_AND_PUBLISH.md).

## Managing controllers

Everything is done on the integration page: **Settings → Devices & services
→ Integrations → Entity Controller**. Each controller is one entry on that
page, with its own device.

| To… | Do this on the integration page |
|---|---|
| Add a controller | **Add controller** (the first time: *Add integration* → search *Entity Controller*) |
| Change any setting | The controller's **Configure** (⚙) button |
| Rename | ⋮ → *Rename* (entity ids are kept) |
| Restart a controller | ⋮ → *Reload* |
| Switch a controller off / on | ⋮ → *Disable* / *Enable* |
| Remove | ⋮ → *Delete* |
| Debug logging | ⋮ at the top right of the page → *Enable debug logging* |
| Bug report data | ⋮ → *Download diagnostics* |
| Activate, clear/enable block, stay mode | Open the controller's **device**: *Activate*, *Clear block* and *Enable block* buttons and a *Stay mode* switch |

### Adding a controller

The first form asks for the essentials:

| Field | Meaning |
|---|---|
| Name | Also defines the entity id, e.g. `Hallway motion` → `entity_controller.hallway_motion` |
| Trigger sensors | Entities that turn the controlled entities on |
| Sensor type | *Event* or *Duration*, see [Sensor types](#sensor-types) |
| Controlled entities | Lights, switches, fans, media players, groups … |
| Delay | Seconds the entities stay on after the last trigger |

Then a menu lets you adjust any other group of settings before choosing
**Create controller**.

### Changing a controller

**Configure** opens the same menu of settings groups. Pick a group, change
it, repeat, then choose **Save** — the controller applies the new settings
immediately (it restarts without switching any light).

### The controller device

Each controller has a device (type *service*) with these entities:

| Entity | Purpose |
|---|---|
| `entity_controller.<name>` | The controller's state (see [States](#states)) and attributes. Used by automations and the `entity_controller.*` actions. |
| `button.<name>_activate` | Turn the entities on and start the timer (also clears *blocked*). |
| `button.<name>_clear_block` | Leave *blocked*, as if the block timeout expired. |
| `button.<name>_enable_block` | Put an active controller into *blocked*. |
| `switch.<name>_stay_mode` | Stay mode — the same setting as in Configure → Timer. |

A button shows an error when its action is not possible in the current state.

## Settings reference

Every setting corresponds to an option of the original YAML configuration
(shown in `code`), so the original
[documentation](https://danobot.github.io/ec-docs/) still explains the
details.

### Sensors

| Setting | YAML | Description |
|---|---|---|
| Trigger sensors | `sensor`, `sensors` | When one of them turns on, the controlled entities are turned on. |
| Sensor type | `sensor_type` | `event` (default) or `duration`. |
| Restart the timer when the sensors turn off | `sensor_resets_timer` | Duration sensors: when the last sensor turns off, run the full delay again. |
| Hold sensors | `hold_sensors` (new) | While any is on the entities stay on, but they never turn them on. |
| Maximum hold time | `max_hold_time` (new) | Seconds. A sensor that has been on for longer no longer keeps the entities on (stuck sensors). Applies to hold sensors and to duration trigger sensors. Empty = no limit. |

### Controlled entities

| Setting | YAML | Description |
|---|---|---|
| Controlled entities | `entity`, `entities` | Turned on/off by the controller, with the service data below. |
| State entities | `state_entities` | Observed instead of the controlled entities to know whether they are on (needed for scenes/scripts). Empty = observe the controlled entities. |
| Call turn_on on activation | `trigger_on_activate` | Entities (usually scripts) on which only `turn_on` is called when activating. |
| Call turn_on on deactivation | `trigger_on_deactivate` | Entities on which `turn_on` is called when deactivating. |

### Timer

| Setting | YAML | Description |
|---|---|---|
| Delay | `delay` | Seconds (default 180). |
| Stay mode | `stay_mode` | After a trigger, leave the entities on until they are turned off manually. |
| Exponential backoff | `backoff` | Each re-trigger while active multiplies the delay by the factor… |
| Backoff factor | `backoff_factor` | …(default 1.1)… |
| Maximum delay with backoff | `backoff_max` | …up to this many seconds (default 300). |

### Service data

`service_data` and `service_data_off` are passed to the `turn_on` / `turn_off`
calls, e.g. `brightness_pct: 50` or `transition: 2`. They are edited as YAML
in the form. For scripts use `variables:`.

Values can be [templates](https://www.home-assistant.io/docs/configuration/templating/),
evaluated every time the controller switches the entities, so the data can
depend on other entities. The motion logic is unchanged:

```yaml
# 50 % while "do not disturb" is on, otherwise 100 %
brightness_pct: "{{ 50 if is_state('input_boolean.dnd', 'on') else 100 }}"
transition: 2
```

A template that fails is logged and only its key is left out.

### Delayed entities

`delayed_entities`, `delayed_after`, `delayed_min_on` (new): entities such as
a bathroom fan that turn on only if the controller stays active for
*Turn on after* seconds, then run for at least *Keep on for at least*
seconds, and after that for as long as the controller stays active.

Bathroom example (light delay X, fan after Y, fan minimum Z):

* Leave before Y → the fan never turns on.
* Stay longer than Y → the fan turns on; leave before Z → the light turns
  off as usual, the fan keeps running until Z is over.
* Stay longer than Z → the fan keeps running until the controller goes idle
  (no more movement), together with the light.

Entities that are already on when Y is reached are left alone. They are
switched with plain `turn_on`/`turn_off` (no service data).
A running fan is remembered across reloads (saving the options) and Home
Assistant restarts, so it still turns off when its time is up.

The controller entity's details show what they are doing: *Delayed status*
(Off, Waiting, On (minimum time), On (until the room is empty)) and
*Delayed until* (when they turn on, or when the minimum time ends).
Its *Activity* (logbook) lists when the controller turned them on, kept
them on until the room was empty, and turned them off.

### Active hours

`start_time` / `end_time`: outside this window the controller is
`constrained` and ignores the sensors. Accepted formats: `22:30:00`,
`22:30`, `sunrise`, `sunset`, `sunset - 00:30:00`, `sunrise + 01:00:00`.
Set both or none.

### Night mode

`night_mode`: a different delay and service data between a night start and
end time (same formats as above). An empty night delay or service data uses
the normal one. Night mode can be switched off without losing its settings.
The `set_night_mode` service changes the times until the next reload.

### Overrides & blocking

| Setting | YAML | Description |
|---|---|---|
| Override entities | `override`, `overrides` | While any is on, the controller is `overridden` and does nothing. |
| Disable blocking | `disable_block` | Take over entities that are already on (and turn them off after the delay). |
| Block timeout | `block_timeout` | Seconds after which a `blocked` controller takes control again. |
| Grace period | `grace_period` | Seconds to ignore state changes of the controlled entities after the controller switched them. Only for integrations whose updates arrive late or without context (some cloud integrations). |

### Transition behaviours

`behaviours`: for each of entering/leaving `idle`, `active`, `overridden`,
`constrained` and `blocked` choose *Turn on*, *Turn off* or *Do nothing*.
Defaults: entering idle turns off, entering active turns on. Use *Turn off*
on *Entering constrained* to switch off lights left on when the active hours end.

### Advanced

| Setting | YAML |
|---|---|
| Ignored attribute changes (e.g. `brightness`, `color_temp` for adaptive lighting) | `state_attributes_ignore` |
| Ignored event sources (regular expressions on the context id) | `ignored_event_sources` |
| Additional on/off states for all entity types | `state_strings_on`, `state_strings_off` |
| On/off states per entity type (replace the defaults) | `sensor_states_on/off`, `control_states_on/off`, `state_states_on/off`, `override_states_on/off` |

Default on states: `on`, `playing`, `home`, `True`. Default off states:
`off`, `idle`, `paused`, `away`, `False`.

## Sensor types

**Event** sensors only say "something happened". Every trigger (re)starts the
timer; when it expires the entities are turned off.

**Duration** sensors stay on while there is motion/presence. The entities stay
on until **all** trigger sensors (and hold sensors) are off **and** the timer
has expired — whichever happens last. With *Restart the timer when the sensors
turn off*, the full delay starts again when the last sensor turns off.

### Motion + presence sensors

Recommended setup for a room with a PIR motion sensor and an mmWave presence
sensor:

* Trigger sensors: the motion sensor (fast, reliable "someone came in")
* Hold sensors: the presence sensor (keeps the light on while you sit still,
  but its false positives never switch the light on)
* Sensor type: Duration

Alternatively put both in *Trigger sensors* with type *Duration* — the
controller stays active while either of them is on.

If a sensor becomes `unavailable`, the controller does not switch off
immediately; it falls back to the timer.

### Stuck sensors: maximum hold time

A presence sensor that gets stuck reporting `on` would keep the lights on
forever. With a *Maximum hold time* (Configure → Sensors), a sensor that has
been on continuously for longer than that no longer keeps the lights on: once
the timer has also expired, they turn off (or the delay runs once more with
*Restart the timer when the sensors turn off*). A warning is logged for the
sensor. The sensor's next off → on change counts as fresh again, and new
triggers keep working.

The limit applies to hold sensors and to trigger sensors of type *Duration*.
Choose more than the longest time someone stays still in that room — someone
watching a long film would otherwise end up in the dark — e.g. `7200` (2 hours).
It is off by default.

## States

| State | Meaning |
|---|---|
| `idle` | Waiting for a trigger. |
| `active_timer` | Entities were turned on, the timer is running (or waiting for duration sensors: `expires_at: pending sensor`). |
| `active_stay_on` | Stay mode: on until turned off manually. |
| `blocked` | A sensor triggered while the entities were already on (e.g. switched on manually): EC leaves them alone until they are turned off. |
| `overridden` | An override entity is on. |
| `constrained` | Outside the active hours. |

Attributes include `last_triggered_by`, `last_triggered_at`, `expires_at`,
`delay`, `mode` (day/night), `blocked_by`, `overridden_by`, `stay_mode` and the
configured entity lists.

After a Home Assistant restart or a reload the controller resumes: if it was
active and the lights are still on, a fresh timer starts; if it was blocked
and the lights are still on, it stays blocked. Saving the options never
switches lights.

## Actions for automations

The device buttons and switch cover these from the UI. For automations and
scripts, the same functions are available as actions targeting
`entity_controller.*` entities:

| Service | Description |
|---|---|
| `entity_controller.activate` | Turn the entities on and start the timer (also clears `blocked`). |
| `entity_controller.clear_block` | Leave `blocked` as if the block timeout expired. |
| `entity_controller.enable_block` | Put an active controller into `blocked`. |
| `entity_controller.enable_stay_mode` / `disable_stay_mode` | Turn stay mode on/off (same as the *Stay mode* switch; saved in the controller's settings). |
| `entity_controller.set_night_mode` | Change the night start/end (`start_time`, `end_time`; also `now` or `constraint`). |

## Migrating from the original Entity Controller / YAML

1. Remove the original *Entity Controller* from HACS (both use the same
   folder `custom_components/entity_controller`).
2. Install this version (see [docs/INSTALL_AND_PUBLISH.md](docs/INSTALL_AND_PUBLISH.md))
   and restart Home Assistant.
3. Your `entity_controller:` YAML controllers are imported once, each as a
   controller on the Entity Controller integration page, with the same entity
   ids (`entity_controller.<friendly name>`). A repair notice lists them.
   Problems (e.g. an invalid `sensor_type`) are logged and listed in a second
   repair notice.
4. Remove the `entity_controller:` section from your YAML and restart. From now
   on the controllers are managed only on the integration page; YAML is never
   read again. (Without an `entity_controller:` section the integration does
   not look at YAML at all.)

## Troubleshooting

Turn on debug logging with ⋮ (top right of the integration page) → *Enable
debug logging*; disabling it again downloads the log. Each controller logs as
`custom_components.entity_controller.<object id>`, e.g.
`custom_components.entity_controller.hallway_motion`.

*Download diagnostics* (⋮ of the controller on the integration page)
contains its settings and the current state of all watched entities.

If the controller ends up `blocked` right after turning lights on, the lights
probably report extra attribute changes (add them to *Ignored attribute
changes*) or report their state late without context (set a *Grace period*).

## Development

```bash
pip install -r requirements_test.txt
pytest
```

The tests use the official custom-component test harness and run against the
Home Assistant version pinned in `requirements_test.txt`. Home Assistant does
not run on Windows; to run the tests there anyway, see the note in
`tests/conftest.py`. UI texts are generated with
`python scripts/generate_translations.py`.

## Credits and license

Entity Controller was created by Daniel Mason ([danobot](https://github.com/danobot));
the original documentation is at <https://danobot.github.io/ec-docs/>. Bug
fixes were also adopted from the forks of Jan Pluskal, Wim Immelman,
floris-b, jddayley and Rob Chandhok — see [CHANGELOG.md](CHANGELOG.md).

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See [COPYING](COPYING). This is a modified version of Entity
Controller 9.7.6, changed in October 2026.
