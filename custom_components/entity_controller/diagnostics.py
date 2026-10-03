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
"""Diagnostics download (Settings -> Devices & services -> ... -> Download diagnostics)."""
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return the controller configuration and its current runtime state."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(DOMAIN, DOMAIN, entry.entry_id)
    state = hass.states.get(entity_id) if entity_id else None
    watched: dict[str, str | None] = {}
    options = dict(entry.options)
    for key in ("sensors", "hold_sensors", "entities", "state_entities", "overrides"):
        for watched_id in options.get(key) or []:
            current = hass.states.get(watched_id)
            watched[watched_id] = current.state if current else None
    return {
        "version": str((await async_get_integration(hass, DOMAIN)).version),
        "title": entry.title,
        "data": dict(entry.data),
        "options": options,
        "entity_id": entity_id,
        "state": state.state if state else None,
        "attributes": dict(state.attributes) if state else None,
        "watched_entity_states": watched,
    }
