# Meshtastic Telegram Bridge

A Home Assistant integration that links a Telegram chat with a Meshtastic channel or node.

- Messages written in the Telegram chat are sent to the mesh through a gateway of the
  [Meshtastic integration](https://github.com/meshtastic/home-assistant), prefixed with the sender's first name.
- Messages received from the mesh are posted in the Telegram chat, prefixed with the node's name.
- Each bridge links one chat with one channel (or one node for direct messages). Add the integration several times
  to bridge more chats.
- With the Mesh Chat build of the Meshtastic integration, bridged messages also appear in the **Mesh Chat** panel,
  labelled `Telegram: <name>`.

The bridge uses only the public actions and events of the Meshtastic and Telegram bot integrations. It stores no
tokens of its own: the Telegram bot token stays in the Telegram bot integration, the gateway connection in the
Meshtastic integration.

## Requirements

- Home Assistant 2025.7 or newer
- The [Meshtastic integration](https://github.com/meshtastic/home-assistant) with at least one gateway
- The built-in [Telegram bot integration](https://www.home-assistant.io/integrations/telegram_bot/) set up with the
  *polling* platform (no public URL needed) or *webhooks*

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/rdkmedia0/meshtastic-telegram-bridge`,
   type *Integration*
2. Download **Meshtastic Telegram Bridge** and restart Home Assistant

### Manual

Copy `custom_components/meshtastic_telegram_bridge` into the `custom_components` folder of your configuration and
restart Home Assistant.

## Setup

1. **Telegram bot**: create a bot with [@BotFather](https://t.me/BotFather) and add the Telegram bot integration in
   Home Assistant with the bot token and the *polling* platform.
2. **Allow the chat**: open the Telegram bot integration → ⋮ → **Add allowed chat ID** and add the chat to bridge.
   Group chats have negative IDs (e.g. `-1001234567890`). The bot only receives messages from allow-listed chats.
   To find the ID, add the bot to the group and look at the `telegram_text` event in
   *Developer tools → Events*, or use a bot like `@userinfobot`.
3. **Groups**: for the bot to see every message in a group, disable its privacy mode in BotFather
   (`/setprivacy` → *Disable*) and re-add the bot to the group, or make it a group admin.
4. **Add the bridge**: Settings → Devices & services → **Add integration** → *Meshtastic Telegram Bridge*.
   Select the gateway, the Telegram bot (optional with a single bot), enter the chat ID and choose the mesh target:
   a channel index of the gateway (0 is the primary channel) or a node for direct messages.

## Options

Open the bridge's entry → **Configure**.

| Option | Default | Description |
|---|---|---|
| Direction | Both | Only forward Telegram to the mesh, only the mesh to Telegram, or both |
| Prefix mesh messages with the Telegram sender's first name | on | `Alice: on my way` on the mesh |
| Prefix Telegram messages with the mesh node's name | on | **Anna Hiking**: `on my way` in Telegram |
| Telegram messages longer than 200 bytes | Split | Split into up to 5 numbered packets (`[1/3]`) or truncate |

## Good to know

- Meshtastic text messages are limited to 200 bytes including the prefix. Keep Telegram messages short; a chatty group
  can quickly use up LoRa airtime. Long messages are split into at most 5 packets, the rest is dropped and logged.
- Every message sent to the mesh comes from the gateway node. The prefix tells mesh users who wrote it.
- Messages the gateway itself sends are never forwarded back to Telegram, so a bridge cannot loop. Two bridges on
  the same chat and channel are rejected.
- Messages sent to the mesh are passed to the `meshtastic.send_text` action with `sent_by: "Telegram: <name>"`.
  The Mesh Chat build of the Meshtastic integration records them in the chat history; other versions ignore the
  label and still send the message.
- Media, stickers and commands (`/...`) are not forwarded.

## Troubleshooting

- *Nothing arrives on the mesh*: check that the chat ID is allow-listed in the Telegram bot integration and that the
  `telegram_text` event fires in *Developer tools → Events* when you write in the chat.
- *Nothing arrives in Telegram*: check that the `meshtastic_api_text_message` event fires for the gateway and that
  the channel index matches the gateway's channel.
- *The bridge shows "not ready"*: the Meshtastic gateway was not loaded yet. The bridge retries automatically.
- Enable debug logging with `logger: logs: custom_components.meshtastic_telegram_bridge: debug`.

## License

MIT
