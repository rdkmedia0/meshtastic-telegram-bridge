# SPDX-FileCopyrightText: 2026 Meshtastic Telegram Bridge contributors
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging
from collections import deque
from html import escape
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

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
    DEDUPLICATE_WINDOW,
    DEFAULT_DIRECTION,
    DEFAULT_LONG_MESSAGES,
    DEFAULT_PREFIX_MESH_SENDER,
    DEFAULT_PREFIX_TELEGRAM_SENDER,
    DIRECTION_TO_MESH,
    DIRECTION_TO_TELEGRAM,
    EVENT_MESHTASTIC_TEXT_MESSAGE,
    EVENT_TELEGRAM_TEXT,
    TARGET_CHANNEL,
    TELEGRAM_DOMAIN,
    TELEGRAM_SERVICE_SEND_MESSAGE,
)
from .mesh import MeshSender, MeshTarget, mesh_event_message, node_display_name, parse_node_id, split_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import Event, HomeAssistant

_LOGGER = logging.getLogger(__name__)


def target_from_entry(entry: ConfigEntry) -> MeshTarget:
    if entry.data[CONF_TARGET_TYPE] == TARGET_CHANNEL:
        return MeshTarget(TARGET_CHANNEL, channel_index=int(entry.data[CONF_CHANNEL_INDEX]))
    return MeshTarget(entry.data[CONF_TARGET_TYPE], node_id=parse_node_id(str(entry.data[CONF_NODE_ID])))


class TelegramMeshBridge:
    """Forwards messages between one Telegram chat and one Meshtastic channel or node."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.chat_id = int(entry.data[CONF_CHAT_ID])
        self.telegram_entry_id: str | None = entry.data.get(CONF_TELEGRAM_ENTRY_ID) or None
        self.target = target_from_entry(entry)
        self.sender = MeshSender(hass, entry.data[CONF_GATEWAY_ENTRY_ID])
        self._unsubscribe: list[Callable[[], None]] = []
        self._seen_packets: deque[tuple[int, Any]] = deque(maxlen=DEDUPLICATE_WINDOW)

    @property
    def direction(self) -> str:
        return self.entry.options.get(CONF_DIRECTION, DEFAULT_DIRECTION)

    async def async_setup(self) -> None:
        await self.sender.async_setup()
        if self.direction != DIRECTION_TO_TELEGRAM:
            self._unsubscribe.append(self.hass.bus.async_listen(EVENT_TELEGRAM_TEXT, self._on_telegram_text))
        if self.direction != DIRECTION_TO_MESH:
            self._unsubscribe.append(self.hass.bus.async_listen(EVENT_MESHTASTIC_TEXT_MESSAGE, self._on_mesh_text))

    async def async_unload(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe.clear()

    # ---------- Telegram -> mesh ----------

    @callback
    def _on_telegram_text(self, event: Event) -> None:
        data = event.data
        if _as_int(data.get("chat_id")) != self.chat_id:
            return
        bot_entry = (data.get("bot") or {}).get("config_entry_id")
        if self.telegram_entry_id and bot_entry and bot_entry != self.telegram_entry_id:
            return
        text = str(data.get("text") or "").strip()
        if not text:
            return

        name = str(data.get("from_first") or data.get("user_id") or "Telegram").strip()
        prefix = (
            f"{name}: " if self.entry.options.get(CONF_PREFIX_TELEGRAM_SENDER, DEFAULT_PREFIX_TELEGRAM_SENDER) else ""
        )
        try:
            chunks, dropped = split_text(
                text, prefix, mode=self.entry.options.get(CONF_LONG_MESSAGES, DEFAULT_LONG_MESSAGES)
            )
        except ValueError:
            _LOGGER.warning("Cannot forward message from %s: the sender name alone exceeds the mesh limit", name)
            return
        if dropped:
            _LOGGER.warning(
                "Message from %s in Telegram chat %s was too long for the mesh, %d bytes were not sent",
                name,
                self.chat_id,
                len(dropped.encode("utf-8")),
            )
        self.hass.async_create_task(self.sender.async_send(self.target, chunks, sent_by=f"Telegram: {name}"))

    # ---------- mesh -> Telegram ----------

    @callback
    def _on_mesh_text(self, event: Event) -> None:
        if self.sender.gateway_num is None:
            return
        match = mesh_event_message(
            event.data,
            gateway_entry_id=self.entry.data[CONF_GATEWAY_ENTRY_ID],
            gateway_num=self.sender.gateway_num,
            target=self.target,
        )
        if match is None:
            return
        from_id, text = match
        packet_id = event.data.get("message_id")
        if packet_id is not None:
            key = (from_id, packet_id)
            if key in self._seen_packets:
                return
            self._seen_packets.append(key)

        if self.entry.options.get(CONF_PREFIX_MESH_SENDER, DEFAULT_PREFIX_MESH_SENDER):
            message = f"<b>{escape(node_display_name(self.hass, from_id))}</b>: {escape(text)}"
        else:
            message = escape(text)
        self.hass.async_create_task(self._async_send_telegram(message))

    async def _async_send_telegram(self, message: str) -> None:
        data: dict[str, Any] = {"message": message, "parse_mode": "html", "chat_id": [self.chat_id]}
        if self.telegram_entry_id:
            data["config_entry_id"] = self.telegram_entry_id
        try:
            await self.hass.services.async_call(TELEGRAM_DOMAIN, TELEGRAM_SERVICE_SEND_MESSAGE, data, blocking=True)
        except HomeAssistantError:
            _LOGGER.warning("Failed to send message to Telegram chat %s", self.chat_id, exc_info=True)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
