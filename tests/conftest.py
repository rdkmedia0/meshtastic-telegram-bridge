# SPDX-FileCopyrightText: 2026 Meshtastic Telegram Bridge contributors
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockModule, mock_integration

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall

GATEWAY = 0x4904
ANNA = 0xA1B2C3D4
CHAT_ID = -1001234567890
TELEGRAM_ENTRY = "telegram-entry"

SEND_TEXT_SCHEMA = vol.Schema(
    {
        vol.Required("text"): str,
        vol.Optional("from"): str,
        vol.Optional("to"): str,
        vol.Optional("channel"): str,
        vol.Optional("ack", default=False): bool,
        vol.Optional("sent_by"): str,
    }
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):  # noqa: ARG001
    return


@pytest.fixture
def mesh(hass: HomeAssistant):
    """Fake the parts of the Meshtastic and Telegram bot integrations the bridge talks to."""
    mock_integration(hass, MockModule("meshtastic"))
    mock_integration(hass, MockModule("telegram_bot"))

    gateway = MockConfigEntry(domain="meshtastic", title="Home Gateway")
    gateway.add_to_hass(hass)
    gateway.runtime_data = SimpleNamespace(gateway_node={"num": GATEWAY})

    sent: list[dict[str, Any]] = []
    telegram: list[dict[str, Any]] = []

    def _send_text(call: ServiceCall) -> None:
        sent.append(dict(call.data))

    def _send_message(call: ServiceCall) -> None:
        telegram.append(dict(call.data))

    hass.services.async_register("meshtastic", "send_text", _send_text, schema=SEND_TEXT_SCHEMA)
    hass.services.async_register("telegram_bot", "send_message", _send_message)
    return SimpleNamespace(gateway=gateway, sent=sent, telegram=telegram)
