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
"""
Entity controller component for Home Assistant.
Original author:  Daniel Mason
Version:          see manifest.json
Documentation:    https://github.com/danobot/entity-controller

Controllers are managed on the integration page (Settings -> Devices &
services -> Integrations -> Entity Controller): one config entry, with its
own device, per controller. Controllers still defined in YAML are imported
once, after which the YAML is not used any more.
"""

from dataclasses import dataclass
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
from homeassistant.util import slugify

from .const import (
    CONF_ENTITY_ID,
    CONF_STAY_MODE,
    CONF_YAML_KEY,
    DOMAIN,
    PLATFORMS,
)
from .controller import build_machine
from .entity import EntityController
from .entity_services import async_setup_entity_services
from .options import legacy_to_options, validate_options

_LOGGER = logging.getLogger(__name__)

# Legacy YAML is validated leniently here and converted by legacy_to_options.
# Keeping a PLATFORM_SCHEMA (instead of a CONFIG_SCHEMA) preserves the way
# Home Assistant merged `entity_controller:` blocks from packages before.
PLATFORM_SCHEMA = cv.schema_with_slug_keys(vol.Any(None, dict))


@dataclass
class ControllerRuntime:
    """Runtime data of one controller (ConfigEntry.runtime_data)."""

    entity: EntityController
    # Options and title the controller was started with.
    options: dict[str, Any]
    title: str


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the entity domain, the services and import YAML controllers."""
    component = EntityComponent(_LOGGER, DOMAIN, hass)
    hass.data[DOMAIN] = {"component": component, "machine": build_machine()}
    async_setup_entity_services(component)

    yaml_blocks = config.get(DOMAIN)
    if yaml_blocks:
        if isinstance(yaml_blocks, dict):
            yaml_blocks = [yaml_blocks]
        # Not awaited: creating config entries waits for this setup to finish.
        hass.async_create_task(
            _async_import_yaml(hass, yaml_blocks), f"{DOMAIN} YAML import", eager_start=False
        )

    integration = await async_get_integration(hass, DOMAIN)
    _LOGGER.info("Entity Controller v%s is ready", integration.version)
    return True


async def _async_import_yaml(hass: HomeAssistant, yaml_blocks: list[dict[str, Any]]) -> None:
    """Import YAML controllers as config entries (once per controller)."""
    imported: list[str] = []
    failed: list[str] = []
    for block in yaml_blocks:
        for key, raw in (block or {}).items():
            try:
                title, options, warnings = legacy_to_options(key, raw)
            except (TypeError, ValueError) as err:
                _LOGGER.error("Cannot import YAML controller '%s': %s", key, err)
                failed.append(key)
                continue
            if errors := validate_options(options):
                _LOGGER.error(
                    "Cannot import YAML controller '%s', invalid options: %s", key, errors
                )
                failed.append(key)
                continue
            for warning in warnings:
                _LOGGER.warning("YAML controller '%s': %s", key, warning)
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data={
                    CONF_YAML_KEY: key,
                    "title": title,
                    "options": options,
                    # Same entity id as the YAML version, so automations keep working.
                    CONF_ENTITY_ID: f"{DOMAIN}.{slugify(title)}",
                },
            )
            if result.get("type") == "create_entry":
                _LOGGER.info("Imported YAML controller '%s' into the UI", key)
            imported.append(key)

    ir.async_create_issue(
        hass,
        DOMAIN,
        "deprecated_yaml",
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="deprecated_yaml",
        translation_placeholders={"controllers": ", ".join(imported) or "-"},
    )
    if failed:
        ir.async_create_issue(
            hass,
            DOMAIN,
            "yaml_import_failed",
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="yaml_import_failed",
            translation_placeholders={"controllers": ", ".join(failed)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, "yaml_import_failed")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one controller from a config entry."""
    data = hass.data[DOMAIN]
    integration = await async_get_integration(hass, DOMAIN)
    entity = EntityController(hass, entry, data["machine"], str(integration.version))
    entry.runtime_data = ControllerRuntime(entity, dict(entry.options), entry.title)

    component: EntityComponent = data["component"]
    if not await component.async_setup_entry(entry):
        return False
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a controller."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    component: EntityComponent = hass.data[DOMAIN]["component"]
    return await component.async_unload_entry(entry)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options or a new name.

    A change of stay mode alone (Stay mode switch, enable/disable_stay_mode
    actions) is applied in place; anything else reloads the controller, which
    resumes its state without switching any entity.
    """
    runtime: ControllerRuntime = entry.runtime_data
    new_options = dict(entry.options)
    ignore = {CONF_STAY_MODE}
    if entry.title == runtime.title and {
        k: v for k, v in new_options.items() if k not in ignore
    } == {k: v for k, v in runtime.options.items() if k not in ignore}:
        runtime.options = new_options
        stay = bool(new_options.get(CONF_STAY_MODE))
        if runtime.entity.model.stay != stay:
            runtime.entity.set_stay_mode(stay)
        return
    await hass.config_entries.async_reload(entry.entry_id)
