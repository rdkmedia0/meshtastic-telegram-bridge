# SPDX-FileCopyrightText: 2026 Meshtastic Telegram Bridge contributors
#
# SPDX-License-Identifier: MIT

"""Bridge a Telegram chat and a Meshtastic channel or node through the Meshtastic integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

from .bridge import TelegramMeshBridge

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type TelegramBridgeConfigEntry = ConfigEntry[TelegramMeshBridge]


async def async_setup_entry(hass: HomeAssistant, entry: TelegramBridgeConfigEntry) -> bool:
    bridge = TelegramMeshBridge(hass, entry)
    await bridge.async_setup()
    entry.runtime_data = bridge
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TelegramBridgeConfigEntry) -> bool:  # noqa: ARG001
    await entry.runtime_data.async_unload()
    return True


async def _async_update_listener(hass: HomeAssistant, entry: TelegramBridgeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
