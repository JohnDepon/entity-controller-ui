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
"""Buttons on each controller's device page: Activate, Clear block, Enable block."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EntityController


@dataclass(frozen=True, kw_only=True)
class ControllerButtonDescription(ButtonEntityDescription):
    press: Callable[[EntityController], bool]
    # Translation key of the error shown when the action is not possible now.
    error: str


BUTTONS = (
    ControllerButtonDescription(
        key="activate",
        translation_key="activate",
        icon="mdi:play-circle-outline",
        press=lambda controller: controller.activate(),
        error="activate_not_possible",
    ),
    ControllerButtonDescription(
        key="clear_block",
        translation_key="clear_block",
        icon="mdi:lock-open-variant-outline",
        press=lambda controller: controller.clear_block(),
        error="not_blocked",
    ),
    ControllerButtonDescription(
        key="enable_block",
        translation_key="enable_block",
        icon="mdi:lock-outline",
        press=lambda controller: controller.enable_block(),
        error="not_active_timer",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller = entry.runtime_data.entity
    async_add_entities(ControllerButton(controller, description) for description in BUTTONS)


class ControllerButton(ButtonEntity):
    """Runs an action of the controller."""

    _attr_has_entity_name = True
    entity_description: ControllerButtonDescription

    def __init__(self, controller: EntityController, description: ControllerButtonDescription) -> None:
        self.entity_description = description
        self._controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_{description.key}"
        self._attr_device_info = controller.device_info

    async def async_press(self) -> None:
        if not self._controller.is_started:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="starting")
        if not self.entity_description.press(self._controller):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=self.entity_description.error,
                translation_placeholders={"state": str(self._controller.model.state)},
            )
