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
"""Stay mode switch on each controller's device page."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SIGNAL_CONTROLLER_UPDATED
from .entity import EntityController


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([StayModeSwitch(entry.runtime_data.entity)])


class StayModeSwitch(SwitchEntity):
    """Same setting as 'Stay mode' in the controller options."""

    _attr_has_entity_name = True
    _attr_translation_key = "stay_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False
    _attr_icon = "mdi:lightbulb-on-outline"

    def __init__(self, controller: EntityController) -> None:
        self._controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_stay_mode"
        self._attr_device_info = controller.device_info

    @property
    def is_on(self) -> bool:
        return bool(self._controller.model.stay)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONTROLLER_UPDATED.format(self._controller.entry.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._controller.set_stay_mode(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._controller.set_stay_mode(False)
        self.async_write_ha_state()
