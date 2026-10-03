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
""" Entity Service Definitions """

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_component import EntityComponent
import homeassistant.util.dt as dt_util

from .const import (
    SERVICE_ACTIVATE,
    SERVICE_CLEAR_BLOCK,
    SERVICE_ENABLE_BLOCK,
    SERVICE_ENABLE_STAY_MODE,
    SERVICE_DISABLE_STAY_MODE,
    SERVICE_SET_NIGHT_MODE,
    CONF_START_TIME,
    CONF_END_TIME,
)

TIME_STR_FORMAT = "%H:%M:%S"


def async_setup_entity_services(component: EntityComponent):
    """ Setup Entity services."""

    component.logger.debug("Setting up entity services")
    component.async_register_entity_service(SERVICE_ACTIVATE, None, "async_activate")
    component.async_register_entity_service(SERVICE_CLEAR_BLOCK, None, "async_clear_block")
    component.async_register_entity_service(SERVICE_ENABLE_BLOCK, None, "async_enable_block")
    component.async_register_entity_service(SERVICE_ENABLE_STAY_MODE, None, "async_enable_stay_mode")
    component.async_register_entity_service(SERVICE_DISABLE_STAY_MODE, None, "async_disable_stay_mode")
    component.async_register_entity_service(
        SERVICE_SET_NIGHT_MODE,
        {vol.Optional(CONF_START_TIME): cv.string, vol.Optional(CONF_END_TIME): cv.string},
        "async_set_night_mode",
    )
    return True


def apply_night_mode_times(model, start_time=None, end_time=None):
    """ Changes the night mode start and/or end times """

    if model is None or model.night_mode is None:
        return

    now = None
    if start_time == 'now':
        now = dt_util.utcnow()
        start_time = dt_util.as_local(now).strftime(TIME_STR_FORMAT)
    elif start_time == 'constraint':
        start_time = model._start_time_private

    if end_time == 'now':
        if now is None:
            now = dt_util.utcnow()
        end_time = dt_util.as_local(now).strftime(TIME_STR_FORMAT)
    elif end_time == 'constraint':
        end_time = model._end_time_private

    if start_time is None and end_time is None:
        start_time = end_time = '00:00:00'

    if start_time is not None:
        model.log.debug("Setting Night Mode Start to: %s", start_time)
        model.night_mode[CONF_START_TIME] = start_time

    if end_time is not None:
        model.log.debug("Setting Night Mode End to: %s", end_time)
        model.night_mode[CONF_END_TIME] = end_time

    model.prepare_service_data()
