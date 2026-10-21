# SPDX-FileCopyrightText: 2026 Meshtastic Telegram Bridge contributors
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshtastic_telegram_bridge.const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_user_form_is_serialised_for_the_frontend(hass: HomeAssistant, hass_client) -> None:
    MockConfigEntry(domain="meshtastic", entry_id="gateway-entry", title="Home Gateway").add_to_hass(hass)
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()

    response = await client.post("/api/config/config_entries/flow", json={"handler": DOMAIN})
    body = await response.text()
    assert response.status == 200, body
    data = await response.json()
    assert data["type"] == "form"
    assert [field["name"] for field in data["data_schema"]] == [
        "gateway_entry_id",
        "chat_id",
        "target_type",
        "channel_index",
        "node_id",
    ]
    # the config_entry selector is not supported by the frontend in flows, only these are
    assert {next(iter(field["selector"])) for field in data["data_schema"]} <= {"select", "text", "number"}
    gateway = data["data_schema"][0]["selector"]["select"]["options"]
    assert gateway == [{"value": "gateway-entry", "label": "Home Gateway"}]
