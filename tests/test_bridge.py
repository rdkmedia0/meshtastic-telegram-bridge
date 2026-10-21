# SPDX-FileCopyrightText: 2026 Meshtastic Telegram Bridge contributors
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshtastic_telegram_bridge.const import (
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
    DIRECTION_TO_MESH,
    DOMAIN,
    LONG_MESSAGES_TRUNCATE,
    MAX_TEXT_BYTES,
)
from custom_components.meshtastic_telegram_bridge.mesh import split_text

from .conftest import ANNA, CHAT_ID, GATEWAY, TELEGRAM_ENTRY

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def setup_bridge(hass: HomeAssistant, mesh: Any, **overrides: Any) -> MockConfigEntry:
    options = overrides.pop("options", {})
    data = {
        CONF_GATEWAY_ENTRY_ID: mesh.gateway.entry_id,
        CONF_TELEGRAM_ENTRY_ID: TELEGRAM_ENTRY,
        CONF_CHAT_ID: CHAT_ID,
        CONF_TARGET_TYPE: "channel",
        CONF_CHANNEL_INDEX: 1,
        CONF_NODE_ID: None,
        **overrides,
    }
    entry = MockConfigEntry(domain=DOMAIN, title="bridge", data=data, options=options)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def fire_telegram(hass: HomeAssistant, text: str, *, chat_id: int = CHAT_ID, bot_entry: str = TELEGRAM_ENTRY) -> None:
    hass.bus.async_fire(
        "telegram_text",
        {
            "chat_id": chat_id,
            "user_id": 42,
            "from_first": "Alice",
            "from_last": "Anderson",
            "text": text,
            "id": 7,
            "bot": {"config_entry_id": bot_entry},
        },
    )


def fire_mesh(  # noqa: PLR0913
    hass: HomeAssistant,
    entry_id: str,
    *,
    text: str = "hi",
    from_id: int = ANNA,
    to_node: int | None = None,
    channel: int | None = 1,
    message_id: int = 1,
) -> None:
    hass.bus.async_fire(
        "meshtastic_api_text_message",
        {
            "config_entry_id": entry_id,
            "node": from_id,
            "data": {"from": from_id, "to": {"node": to_node, "channel": channel}, "gateway": GATEWAY, "message": text},
            "message_id": message_id,
        },
    )


async def test_telegram_to_mesh_channel(hass: HomeAssistant, mesh) -> None:
    entry = await setup_bridge(hass, mesh)
    assert entry.state is ConfigEntryState.LOADED

    fire_telegram(hass, "  on my way ")
    fire_telegram(hass, "other chat", chat_id=123)
    fire_telegram(hass, "other bot", bot_entry="another-bot")
    await hass.async_block_till_done()

    assert mesh.sent == [
        {"from": str(GATEWAY), "channel": "1", "text": "Alice: on my way", "ack": False, "sent_by": "Telegram: Alice"}
    ]

    assert await hass.config_entries.async_unload(entry.entry_id)
    fire_telegram(hass, "after unload")
    await hass.async_block_till_done()
    assert len(mesh.sent) == 1


async def test_long_telegram_message_is_split(hass: HomeAssistant, mesh) -> None:
    await setup_bridge(hass, mesh)

    fire_telegram(hass, " ".join(f"word{i}" for i in range(60)))
    await hass.async_block_till_done()

    texts = [call["text"] for call in mesh.sent]
    assert len(texts) == 3
    assert all(len(t.encode()) <= MAX_TEXT_BYTES for t in texts)
    assert texts[0].startswith("Alice: word0 ")
    assert texts[0].endswith(" [1/3]")
    assert texts[-1].endswith("word59 [3/3]")


async def test_long_telegram_message_is_truncated(hass: HomeAssistant, mesh) -> None:
    await setup_bridge(
        hass, mesh, options={CONF_LONG_MESSAGES: LONG_MESSAGES_TRUNCATE, CONF_PREFIX_TELEGRAM_SENDER: False}
    )

    fire_telegram(hass, "x" * 300)
    await hass.async_block_till_done()

    assert len(mesh.sent) == 1
    assert mesh.sent[0]["text"] == "x" * 197 + "..."


async def test_mesh_to_telegram(hass: HomeAssistant, mesh) -> None:
    entry = await setup_bridge(hass, mesh)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=mesh.gateway.entry_id, identifiers={("meshtastic", str(ANNA))}, name="Anna <Hiking>"
    )

    fire_mesh(hass, mesh.gateway.entry_id, text="hello & bye", message_id=10)
    fire_mesh(hass, mesh.gateway.entry_id, text="hello & bye", message_id=10)  # reported twice by the gateway
    fire_mesh(hass, mesh.gateway.entry_id, text="other channel", channel=2, message_id=11)
    fire_mesh(hass, mesh.gateway.entry_id, text="direct", to_node=GATEWAY, channel=None, message_id=12)
    fire_mesh(hass, mesh.gateway.entry_id, text="from the gateway", from_id=GATEWAY, message_id=13)
    fire_mesh(hass, "other-gateway", text="other gateway", message_id=14)
    fire_mesh(hass, mesh.gateway.entry_id, text="unknown node", from_id=0x1234, message_id=15)
    await hass.async_block_till_done()

    assert mesh.telegram == [
        {
            "message": "<b>Anna &lt;Hiking&gt;</b>: hello &amp; bye",
            "parse_mode": "html",
            "chat_id": [CHAT_ID],
            "config_entry_id": TELEGRAM_ENTRY,
        },
        {
            "message": "<b>!00001234</b>: unknown node",
            "parse_mode": "html",
            "chat_id": [CHAT_ID],
            "config_entry_id": TELEGRAM_ENTRY,
        },
    ]

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_mesh_to_telegram_without_prefix_and_bot(hass: HomeAssistant, mesh) -> None:
    await setup_bridge(hass, mesh, options={CONF_PREFIX_MESH_SENDER: False}, **{CONF_TELEGRAM_ENTRY_ID: None})

    fire_mesh(hass, mesh.gateway.entry_id, text="plain")
    await hass.async_block_till_done()

    assert mesh.telegram == [{"message": "plain", "parse_mode": "html", "chat_id": [CHAT_ID]}]


async def test_node_target_uses_direct_messages(hass: HomeAssistant, mesh) -> None:
    await setup_bridge(hass, mesh, **{CONF_TARGET_TYPE: "node", CONF_NODE_ID: "!a1b2c3d4"})

    fire_telegram(hass, "ping")
    fire_mesh(hass, mesh.gateway.entry_id, text="pong", to_node=GATEWAY, channel=None, message_id=1)
    fire_mesh(hass, mesh.gateway.entry_id, text="on a channel", message_id=2)
    fire_mesh(hass, mesh.gateway.entry_id, text="other node", from_id=0x1234, to_node=GATEWAY, channel=None)
    await hass.async_block_till_done()

    assert mesh.sent == [
        {"from": str(GATEWAY), "to": str(ANNA), "text": "Alice: ping", "ack": False, "sent_by": "Telegram: Alice"}
    ]
    assert [m["message"] for m in mesh.telegram] == ["<b>!a1b2c3d4</b>: pong"]


async def test_direction_to_mesh_only(hass: HomeAssistant, mesh) -> None:
    await setup_bridge(hass, mesh, options={CONF_DIRECTION: DIRECTION_TO_MESH})

    fire_telegram(hass, "ping")
    fire_mesh(hass, mesh.gateway.entry_id, text="pong")
    await hass.async_block_till_done()

    assert len(mesh.sent) == 1
    assert mesh.telegram == []


async def test_without_sent_by_support(hass: HomeAssistant, mesh) -> None:
    sent: list[dict[str, Any]] = []
    hass.services.async_remove("meshtastic", "send_text")
    hass.services.async_register(
        "meshtastic",
        "send_text",
        lambda call: sent.append(dict(call.data)),
        schema=vol.Schema(
            {
                vol.Required("text"): str,
                vol.Optional("from"): str,
                vol.Optional("channel"): str,
                vol.Optional("ack"): bool,
            }
        ),
    )
    await setup_bridge(hass, mesh)

    fire_telegram(hass, "ping")
    await hass.async_block_till_done()
    assert sent == [{"from": str(GATEWAY), "channel": "1", "text": "Alice: ping", "ack": False}]


async def test_not_ready_without_gateway(hass: HomeAssistant, mesh) -> None:
    entry = await setup_bridge(hass, mesh, **{CONF_GATEWAY_ENTRY_ID: "missing"})
    assert entry.state is ConfigEntryState.SETUP_RETRY

    mesh.gateway.runtime_data = None
    entry = await setup_bridge(hass, mesh, **{CONF_CHANNEL_INDEX: 2})
    assert entry.state is ConfigEntryState.SETUP_RETRY

    hass.services.async_remove("meshtastic", "send_text")
    mesh.gateway.runtime_data = type("Runtime", (), {"gateway_node": {"num": GATEWAY}})()
    entry = await setup_bridge(hass, mesh, **{CONF_CHANNEL_INDEX: 3})
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_options_update_reloads(hass: HomeAssistant, mesh) -> None:
    entry = await setup_bridge(hass, mesh)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_DIRECTION: DIRECTION_TO_MESH,
            CONF_PREFIX_TELEGRAM_SENDER: False,
            CONF_PREFIX_MESH_SENDER: True,
            CONF_LONG_MESSAGES: LONG_MESSAGES_TRUNCATE,
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options[CONF_DIRECTION] == DIRECTION_TO_MESH
    assert entry.state is ConfigEntryState.LOADED

    fire_telegram(hass, "ping")
    fire_mesh(hass, mesh.gateway.entry_id, text="pong")
    await hass.async_block_till_done()
    assert mesh.sent[-1]["text"] == "ping"
    assert mesh.telegram == []


@pytest.mark.parametrize(
    ("text", "prefix", "mode", "expected", "dropped"),
    [
        ("hello", "A: ", "split", ["A: hello"], ""),
        ("  ", "A: ", "split", [], ""),
        ("héllo wörld " * 20, "", "truncate", None, None),
    ],
)
def test_split_text(text, prefix, mode, expected, dropped) -> None:
    chunks, rest = split_text(text, prefix, mode=mode)
    if expected is not None:
        assert chunks == expected
        assert rest == dropped
    for chunk in chunks:
        assert len(chunk.encode()) <= MAX_TEXT_BYTES
    if expected is None:
        assert chunks[0].endswith("...")
        assert rest


def test_split_text_limits() -> None:
    chunks, rest = split_text("word " * 500, "Bob: ", max_chunks=5)
    assert len(chunks) == 5
    assert chunks[0].startswith("Bob: word word")
    assert chunks[4].endswith(" [5/5]")
    assert rest.startswith("word")
    assert all(len(c.encode()) <= MAX_TEXT_BYTES for c in chunks)

    with pytest.raises(ValueError, match="prefix"):
        split_text("x", "p" * 200)


def fire_chat_sent(  # noqa: PLR0913
    hass: HomeAssistant,
    entry_id: str,
    *,
    text: str = "from the panel",
    sent_by: str | None = "Steve Smith",
    channel: int | None = 1,
    to_node: int | None = None,
    message_id: str = "m1",
    prefix: str | None = None,
) -> None:
    hass.bus.async_fire(
        "meshtastic_chat_message_sent",
        {
            "config_entry_id": entry_id,
            "gateway": GATEWAY,
            "message_id": message_id,
            "to": {"node": to_node, "channel": channel},
            "message": text,
            "prefix": prefix,
            "sent_by": sent_by,
            "status": "sent",
        },
    )


async def test_messages_sent_from_home_assistant_are_mirrored(hass: HomeAssistant, mesh) -> None:
    entry = await setup_bridge(hass, mesh)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=mesh.gateway.entry_id, identifiers={("meshtastic", str(GATEWAY))}, name="Home Gateway"
    )
    gateway = mesh.gateway.entry_id

    fire_chat_sent(hass, gateway, message_id="1")  # from the Mesh Chat panel
    fire_chat_sent(hass, gateway, message_id="1")  # duplicate
    fire_chat_sent(hass, gateway, text="Alice: hi", sent_by="Telegram: Alice", message_id="2")  # our own, skipped
    fire_chat_sent(hass, gateway, text="Bob: hi", sent_by="WhatsApp: Bob", message_id="3")  # another bridge
    fire_chat_sent(hass, gateway, text="automation", sent_by=None, message_id="4")
    fire_chat_sent(hass, gateway, text="Steve S.: prefixed", prefix="Steve S.", message_id="4b")
    fire_chat_sent(hass, gateway, text="other channel", channel=2, message_id="5")
    fire_chat_sent(hass, gateway, text="direct", channel=None, to_node=ANNA, message_id="6")
    fire_chat_sent(hass, "other-gateway", text="other gateway", message_id="7")
    await hass.async_block_till_done()

    assert [m["message"] for m in mesh.telegram] == [
        "<b>Steve Smith</b>: from the panel",
        "<b>WhatsApp: Bob</b>: hi",
        "<b>Home Gateway</b>: automation",
        "<b>Steve Smith</b>: prefixed",
    ]
    assert mesh.sent == []

    assert await hass.config_entries.async_unload(entry.entry_id)
