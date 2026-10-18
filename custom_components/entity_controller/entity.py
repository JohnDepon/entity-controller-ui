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
"""The entity_controller.<name> entity exposing a controller's state.

Every controller (config entry) has one device. Its main entity is this
entity, in the entity_controller domain, so existing automations and the
entity_controller.* services keep working. The device also carries the
button and switch entities (see button.py and switch.py).
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.restore_state import RestoredExtraData, RestoreEntity

from .const import (
    CONF_DELAY,
    CONF_ENTITY_ID,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_STATE_ENTITIES,
    CONF_STAY_MODE,
    DOMAIN,
    SIGNAL_CONTROLLER_UPDATED,
)
from .controller import Model
from .entity_services import apply_night_mode_times
from .options import complete_options

_LOGGER = logging.getLogger(__package__)

PERSISTED_STATE_ATTRIBUTES = [
    "last_triggered_by",
    "last_triggered_at",
    CONF_STATE_ENTITIES,
    "control_entities",
    "sensor_entities",
    "hold_sensor_entities",
    "override_entities",
    CONF_DELAY,
    "sensor_type",
    "mode",
    "start",
    "end",
    CONF_START_TIME,
    CONF_END_TIME,
    "stay_mode",
    # Delayed entities may keep running while the controller is idle.
    "delayed_entities",
    "delayed_status",
    "delayed_until",
]

ICONS = {
    "idle": "mdi:circle-outline",
    "active": "mdi:check-circle",
    "active_timer": "mdi:timer-outline",
    "active_stay_on": "mdi:check-circle",
    "constrained": "mdi:cancel",
    "overridden": "mdi:timer-off-outline",
    "blocked": "mdi:close-circle",
}


def controller_device_info(entry: ConfigEntry, version: str | None) -> DeviceInfo:
    """Device representing one controller on the integration page."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Entity Controller",
        model="Controller",
        sw_version=version,
        entry_type=DeviceEntryType.SERVICE,
    )


class EntityController(RestoreEntity):
    """Entity representing one Entity Controller instance."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    # The main feature of the device: the entity is named after the device.
    _attr_name = None

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, machine, version: str | None
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.attributes: dict[str, Any] = {}
        self.may_update = False
        self._write_scheduled = False
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = controller_device_info(entry, version)
        if requested := entry.data.get(CONF_ENTITY_ID):
            # Imported from YAML: keep the entity id automations already use.
            self.entity_id = requested
        self.model = Model(
            hass,
            name=entry.title,
            instance_id=entry.entry_id,
            options=complete_options(dict(entry.options)),
            machine=machine,
            entity=self,
        )

    @property
    def state(self):
        """Return the state of the entity."""
        return self.model.state

    @property
    def icon(self):
        """Return the entity icon."""
        return ICONS.get(self.model.state, "mdi:eye")

    @property
    def extra_restore_state_data(self) -> RestoredExtraData:
        """Saved (not shown) across reloads and restarts."""
        return RestoredExtraData(self.model.delayed_restore_data())

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the entity."""
        return self.attributes.copy()

    def reset_state(self):
        """ Reset state attributes by removing any state specific attributes when returning to idle state """
        self.attributes = {
            k: v for k, v in self.attributes.items() if k in PERSISTED_STATE_ATTRIBUTES
        }
        self.do_update()

    @callback
    def do_update(self, wait=False, **kwargs):
        """Schedule a (coalesced) entity state write."""
        if not self.may_update or self._write_scheduled:
            return
        self._write_scheduled = True
        # A tracked task (not eager): runs after the current transition has
        # completed, so one transition results in one state write.
        self.hass.async_create_task(
            self._async_flush_state(), f"{DOMAIN} state write", eager_start=False
        )

    async def _async_flush_state(self) -> None:
        self._write_scheduled = False
        if self.may_update:
            self.async_write_ha_state()
            async_dispatcher_send(
                self.hass, SIGNAL_CONTROLLER_UPDATED.format(self.entry.entry_id)
            )

    def set_attr(self, k, v):
        if k == CONF_DELAY:
            v = str(v) + "s"
        self.attributes[k] = v

    async def async_added_to_hass(self) -> None:
        """Restore the previous state and start the controller."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        self.model.restored_state = last_state.state if last_state else None
        extra = await self.async_get_last_extra_data()
        self.model.restored_extra = extra.as_dict() if extra else None
        # Per controller logger: custom_components.entity_controller.<object id>
        self.model.log = logging.getLogger(f"{__package__}.{self.entity_id.split('.', 1)[1]}")
        self.may_update = True
        self.model.async_start()

    async def async_will_remove_from_hass(self) -> None:
        """Stop the controller."""
        self.may_update = False
        self.model.async_shutdown()

    # =====================================================
    #    A C T I O N S   (services, buttons and switch)
    # =====================================================

    @property
    def is_started(self) -> bool:
        return self.model.state != "pending"

    def activate(self) -> bool:
        """Turn the entities on and start the timer (also clears blocked)."""
        if not self.is_started:
            return False
        self.model.log.debug("Activating the Entity Controller")
        return bool(self.model._safe_trigger("activate"))

    def clear_block(self) -> bool:
        """Leave the blocked state as if the block timeout expired."""
        if self.model.state != "blocked":
            return False
        self.model.log.debug("Clearing Blocked state")
        return bool(self.model._safe_trigger("block_timer_expires"))

    def enable_block(self) -> bool:
        """Put an active controller into the blocked state."""
        if self.model.state != "active_timer":
            return False
        self.model.log.debug("Enabling Blocked state")
        return bool(self.model._safe_trigger("block_enable"))

    @callback
    def set_stay_mode(self, value: bool) -> None:
        """Change stay mode. It is saved in the controller's options, so the
        Configure dialog shows it and it survives restarts. It applies from
        the next activation."""
        self.model.log.debug("Stay mode %s", "enabled" if value else "disabled")
        self.model.stay = value
        self.model.update(stay_mode=value)
        if bool(self.entry.options.get(CONF_STAY_MODE)) != value:
            # Applied in place by the update listener (no reload).
            self.hass.config_entries.async_update_entry(
                self.entry, options={**self.entry.options, CONF_STAY_MODE: value}
            )

    # Entity services (entity_controller.*). Invalid requests are ignored, as
    # in the original, so automations do not fail.

    async def async_activate(self) -> None:
        if not self.activate():
            self.model.log.info(
                "activate ignored: not possible from state '%s'", self.model.state
            )

    async def async_clear_block(self) -> None:
        self.clear_block()

    async def async_enable_block(self) -> None:
        self.enable_block()

    async def async_enable_stay_mode(self) -> None:
        self.set_stay_mode(True)

    async def async_disable_stay_mode(self) -> None:
        self.set_stay_mode(False)

    async def async_set_night_mode(self, start_time=None, end_time=None) -> None:
        """Changes the night mode start and/or end times (until the next reload)."""
        apply_night_mode_times(self.model, start_time, end_time)
