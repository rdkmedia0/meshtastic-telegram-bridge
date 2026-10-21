# SPDX-FileCopyrightText: 2026 Meshtastic Telegram Bridge contributors
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CHANNEL_INDEX,
    CONF_CHAT_ID,
    CONF_DIRECTION,
    CONF_GATEWAY_ENTRY_ID,
    CONF_LONG_MESSAGES,
    CONF_NODE_ID,
    CONF_PREFIX_MESH_SENDER,
    CONF_PREFIX_TELEGRAM_SENDER,
    CONF_TARGET_TYPE,
    CONF_TELEGRAM_ENTRY_ID,
    DEFAULT_DIRECTION,
    DEFAULT_LONG_MESSAGES,
    DEFAULT_PREFIX_MESH_SENDER,
    DEFAULT_PREFIX_TELEGRAM_SENDER,
    DIRECTION_BOTH,
    DIRECTION_TO_MESH,
    DIRECTION_TO_TELEGRAM,
    DOMAIN,
    LONG_MESSAGES_SPLIT,
    LONG_MESSAGES_TRUNCATE,
    MESHTASTIC_DOMAIN,
    TARGET_CHANNEL,
    TARGET_NODE,
    TELEGRAM_DOMAIN,
)
from .mesh import parse_node_id

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
    from homeassistant.core import HomeAssistant

MAX_CHANNEL_INDEX = 7


def _entry_selector(hass: HomeAssistant, domain: str) -> selector.SelectSelector:
    """Dropdown of the config entries of an integration (the config_entry selector cannot be used in flows)."""
    options = [
        selector.SelectOptionDict(value=entry.entry_id, label=entry.title)
        for entry in hass.config_entries.async_entries(domain)
    ]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
    )


def _user_schema(hass: HomeAssistant, defaults: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_GATEWAY_ENTRY_ID, default=defaults.get(CONF_GATEWAY_ENTRY_ID, vol.UNDEFINED)): (
            _entry_selector(hass, MESHTASTIC_DOMAIN)
        )
    }
    if hass.config_entries.async_entries(TELEGRAM_DOMAIN):
        fields[vol.Optional(CONF_TELEGRAM_ENTRY_ID, default=defaults.get(CONF_TELEGRAM_ENTRY_ID, vol.UNDEFINED))] = (
            _entry_selector(hass, TELEGRAM_DOMAIN)
        )
    fields.update(
        {
            vol.Required(CONF_CHAT_ID, default=defaults.get(CONF_CHAT_ID, vol.UNDEFINED)): selector.TextSelector(),
            vol.Required(CONF_TARGET_TYPE, default=defaults.get(CONF_TARGET_TYPE, TARGET_CHANNEL)): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[TARGET_CHANNEL, TARGET_NODE],
                        translation_key=CONF_TARGET_TYPE,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            ),
            vol.Optional(CONF_CHANNEL_INDEX, default=defaults.get(CONF_CHANNEL_INDEX, 0)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=MAX_CHANNEL_INDEX, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(CONF_NODE_ID, default=defaults.get(CONF_NODE_ID, vol.UNDEFINED)): selector.TextSelector(),
        }
    )
    return vol.Schema(fields)


def _options_schema(options: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_DIRECTION, default=options.get(CONF_DIRECTION, DEFAULT_DIRECTION)): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[DIRECTION_BOTH, DIRECTION_TO_MESH, DIRECTION_TO_TELEGRAM],
                        translation_key=CONF_DIRECTION,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            ),
            vol.Required(
                CONF_PREFIX_TELEGRAM_SENDER,
                default=options.get(CONF_PREFIX_TELEGRAM_SENDER, DEFAULT_PREFIX_TELEGRAM_SENDER),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_PREFIX_MESH_SENDER, default=options.get(CONF_PREFIX_MESH_SENDER, DEFAULT_PREFIX_MESH_SENDER)
            ): selector.BooleanSelector(),
            vol.Required(CONF_LONG_MESSAGES, default=options.get(CONF_LONG_MESSAGES, DEFAULT_LONG_MESSAGES)): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[LONG_MESSAGES_SPLIT, LONG_MESSAGES_TRUNCATE],
                        translation_key=CONF_LONG_MESSAGES,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            ),
        }
    )


def validate_target(user_input: dict[str, Any], errors: dict[str, str]) -> dict[str, Any]:
    """Normalise the user input of the user step, collecting errors per field."""
    data: dict[str, Any] = {
        CONF_GATEWAY_ENTRY_ID: user_input[CONF_GATEWAY_ENTRY_ID],
        CONF_TELEGRAM_ENTRY_ID: user_input.get(CONF_TELEGRAM_ENTRY_ID) or None,
        CONF_TARGET_TYPE: user_input[CONF_TARGET_TYPE],
    }
    try:
        data[CONF_CHAT_ID] = int(str(user_input[CONF_CHAT_ID]).strip())
    except ValueError:
        errors[CONF_CHAT_ID] = "invalid_chat_id"

    if user_input[CONF_TARGET_TYPE] == TARGET_CHANNEL:
        data[CONF_CHANNEL_INDEX] = int(user_input.get(CONF_CHANNEL_INDEX, 0))
    else:
        node_id = str(user_input.get(CONF_NODE_ID) or "").strip()
        if not node_id:
            errors[CONF_NODE_ID] = "node_id_required"
        else:
            try:
                data[CONF_NODE_ID] = f"!{parse_node_id(node_id):08x}"
            except ValueError:
                errors[CONF_NODE_ID] = "invalid_node_id"
    return data


def _target_label(data: dict[str, Any]) -> str:
    if data[CONF_TARGET_TYPE] == TARGET_CHANNEL:
        return f"channel {data[CONF_CHANNEL_INDEX]}"
    return f"node {data[CONF_NODE_ID]}"


def _unique_id(data: dict[str, Any]) -> str:
    return f"{data[CONF_GATEWAY_ENTRY_ID]}|{_target_label(data)}|{data[CONF_CHAT_ID]}"


class MeshtasticTelegramBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self.hass.config_entries.async_entries(MESHTASTIC_DOMAIN):
            return self.async_abort(reason="no_gateway")
        errors: dict[str, str] = {}
        if user_input is not None:
            data = validate_target(user_input, errors)
            if not errors:
                await self.async_set_unique_id(_unique_id(data))
                self._abort_if_unique_id_configured()
                title = f"Telegram {data[CONF_CHAT_ID]} and {_target_label(data)}"
                return self.async_create_entry(title=title, data=data, options={})
        return self.async_show_form(
            step_id="user", data_schema=_user_schema(self.hass, user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:  # noqa: ARG004
        return MeshtasticTelegramBridgeOptionsFlow()


class MeshtasticTelegramBridgeOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=_options_schema(dict(self.config_entry.options)))
