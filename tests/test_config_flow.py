# SPDX-FileCopyrightText: 2026 Meshtastic Telegram Bridge contributors
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.meshtastic_telegram_bridge.const import (
    CONF_CHANNEL_INDEX,
    CONF_CHAT_ID,
    CONF_GATEWAY_ENTRY_ID,
    CONF_NODE_ID,
    CONF_TARGET_TYPE,
    CONF_TELEGRAM_ENTRY_ID,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def no_setup():
    with patch("custom_components.meshtastic_telegram_bridge.async_setup_entry", AsyncMock(return_value=True)):
        yield


async def test_user_flow_channel(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_GATEWAY_ENTRY_ID: "gateway-entry",
            CONF_TELEGRAM_ENTRY_ID: "telegram-entry",
            CONF_CHAT_ID: " -1001234567890 ",
            CONF_TARGET_TYPE: "channel",
            CONF_CHANNEL_INDEX: 2.0,
        },
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Telegram -1001234567890 and channel 2"
    assert result["data"] == {
        CONF_GATEWAY_ENTRY_ID: "gateway-entry",
        CONF_TELEGRAM_ENTRY_ID: "telegram-entry",
        CONF_CHAT_ID: -1001234567890,
        CONF_TARGET_TYPE: "channel",
        CONF_CHANNEL_INDEX: 2,
    }

    # the same chat and target cannot be bridged twice
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_GATEWAY_ENTRY_ID: "gateway-entry",
            CONF_CHAT_ID: "-1001234567890",
            CONF_TARGET_TYPE: "channel",
            CONF_CHANNEL_INDEX: 2,
        },
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_user_flow_node_and_errors(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_GATEWAY_ENTRY_ID: "gateway-entry", CONF_CHAT_ID: "abc", CONF_TARGET_TYPE: "node"},
    )
    assert result["type"] == "form"
    assert result["errors"] == {CONF_CHAT_ID: "invalid_chat_id", CONF_NODE_ID: "node_id_required"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_GATEWAY_ENTRY_ID: "gateway-entry",
            CONF_CHAT_ID: "42",
            CONF_TARGET_TYPE: "node",
            CONF_NODE_ID: "!xyz",
        },
    )
    assert result["errors"] == {CONF_NODE_ID: "invalid_node_id"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_GATEWAY_ENTRY_ID: "gateway-entry",
            CONF_CHAT_ID: "42",
            CONF_TARGET_TYPE: "node",
            CONF_NODE_ID: str(0xA1B2C3D4),
        },
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Telegram 42 and node !a1b2c3d4"
    assert result["data"][CONF_NODE_ID] == "!a1b2c3d4"
    assert result["data"][CONF_TELEGRAM_ENTRY_ID] is None
