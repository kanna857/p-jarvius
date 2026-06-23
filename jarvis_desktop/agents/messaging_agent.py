"""
JARVIS Messaging Agent — WhatsApp Web & Telegram Bot
─────────────────────────────────────────────────────
WhatsApp: Uses pywhatkit for sending messages via WhatsApp Web.
Telegram: Uses python-telegram-bot for a lightweight bot.

NOTE: WhatsApp requires a logged-in Chrome + WhatsApp Web session.
      Telegram requires a bot token from @BotFather.
"""

import time
import threading
from pathlib import Path
from utils.logger import JarvisLogger


class MessagingAgent:
    """Handles WhatsApp and Telegram messaging for JARVIS."""

    def __init__(self, config=None):
        self.config = config
        self.logger = JarvisLogger("Messaging")
        self._telegram_bot = None
        self._telegram_polling = False
        self.telegram_messages = []  # Store incoming messages
        self.logger.success("Messaging agent ready")

    # ─────────────────────────────────────────────────────────────────────────
    # WhatsApp (via pywhatkit — opens WhatsApp Web in browser)
    # ─────────────────────────────────────────────────────────────────────────

    def send_whatsapp(self, phone: str, message: str, instant: bool = True) -> str:
        """
        Send a WhatsApp message.

        Args:
            phone: Phone number with country code (e.g. '+919876543210')
            message: Text to send
            instant: If True, sends via pywhatkit.sendwhatmsg_instantly (faster)
        """
        try:
            import pywhatkit
        except ImportError:
            return ("⚠️ pywhatkit not installed. "
                    "Run: pip install pywhatkit")

        # Normalize phone
        phone = phone.strip()
        if not phone.startswith("+"):
            phone = "+91" + phone  # Default India country code

        try:
            if instant:
                pywhatkit.sendwhatmsg_instantly(
                    phone, message, wait_time=8, tab_close=True
                )
            else:
                # Schedule 1 minute from now
                import datetime
                now = datetime.datetime.now()
                h, m = now.hour, now.minute + 1
                if m >= 60:
                    m -= 60
                    h += 1
                pywhatkit.sendwhatmsg(phone, message, h, m, tab_close=True)

            self.logger.success(f"WhatsApp → {phone}: '{message[:40]}'")
            return f"✅ WhatsApp message sent to {phone}."

        except Exception as e:
            self.logger.warning(f"WhatsApp send failed: {e}")
            return f"❌ WhatsApp failed: {e}. Make sure WhatsApp Web is logged in."

    def send_whatsapp_group(self, group_id: str, message: str) -> str:
        """Send a message to a WhatsApp group."""
        try:
            import pywhatkit
            pywhatkit.sendwhatmsg_to_group_instantly(
                group_id, message, wait_time=8, tab_close=True
            )
            return f"✅ Sent to WhatsApp group."
        except ImportError:
            return "⚠️ pywhatkit not installed."
        except Exception as e:
            return f"❌ WhatsApp group send failed: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # Telegram Bot
    # ─────────────────────────────────────────────────────────────────────────

    def _get_telegram_token(self) -> str:
        """Get Telegram bot token from config or .env."""
        if self.config and hasattr(self.config, 'TELEGRAM_BOT_TOKEN'):
            return getattr(self.config, 'TELEGRAM_BOT_TOKEN', '')
        return ''

    def _get_telegram_chat_id(self) -> str:
        """Get default Telegram chat ID."""
        if self.config and hasattr(self.config, 'TELEGRAM_CHAT_ID'):
            return getattr(self.config, 'TELEGRAM_CHAT_ID', '')
        return ''

    def send_telegram(self, message: str, chat_id: str = None) -> str:
        """
        Send a Telegram message using the bot API.
        Uses requests directly for zero-dependency simplicity.
        """
        token = self._get_telegram_token()
        if not token:
            return ("⚠️ Telegram bot token not configured. "
                    "Add TELEGRAM_BOT_TOKEN to your .env file. "
                    "Get one from @BotFather on Telegram.")

        chat_id = chat_id or self._get_telegram_chat_id()
        if not chat_id:
            return ("⚠️ No chat_id specified and no default configured. "
                    "Add TELEGRAM_CHAT_ID to your .env or provide one.")

        import requests
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                self.logger.success(f"Telegram → {chat_id}: '{message[:40]}'")
                return "✅ Telegram message sent."
            else:
                error = resp.json().get("description", "Unknown error")
                return f"❌ Telegram error: {error}"
        except Exception as e:
            return f"❌ Telegram send failed: {e}"

    def start_telegram_listener(self, command_callback=None) -> str:
        """
        Starts a background Telegram polling listener.
        Incoming messages are forwarded to command_callback(text) if provided.
        """
        token = self._get_telegram_token()
        if not token:
            return "⚠️ No Telegram bot token configured."

        if self._telegram_polling:
            return "Telegram listener is already running."

        def _poll():
            import requests
            offset = 0
            self._telegram_polling = True
            self.logger.info("Telegram polling listener started.")

            while self._telegram_polling:
                try:
                    url = f"https://api.telegram.org/bot{token}/getUpdates"
                    params = {"offset": offset, "timeout": 30}
                    resp = requests.get(url, params=params, timeout=35)

                    if resp.status_code != 200:
                        time.sleep(5)
                        continue

                    data = resp.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        msg = update.get("message", {})
                        text = msg.get("text", "")
                        chat_id = msg.get("chat", {}).get("id", "")
                        user = msg.get("from", {}).get("first_name", "User")

                        if text:
                            self.logger.info(f"Telegram [{user}]: {text}")
                            self.telegram_messages.append({
                                "from": user, "text": text,
                                "chat_id": chat_id, "time": time.time()
                            })

                            # Forward to JARVIS command processor if callback is set
                            if command_callback:
                                try:
                                    reply = command_callback(text)
                                    self.send_telegram(reply, chat_id=str(chat_id))
                                except Exception as e:
                                    self.logger.warning(f"Telegram command processing error: {e}")

                except Exception as e:
                    self.logger.warning(f"Telegram poll error: {e}")
                    time.sleep(5)

        threading.Thread(target=_poll, daemon=True, name="TelegramPoll").start()
        return "✅ Telegram listener started — I'll respond to messages from your bot."

    def stop_telegram_listener(self):
        self._telegram_polling = False
        self.logger.info("Telegram polling stopped.")
        return "Telegram listener stopped."

    def get_telegram_messages(self, count: int = 5) -> str:
        """Returns the last N received Telegram messages."""
        if not self.telegram_messages:
            return "No Telegram messages received yet."
        recent = self.telegram_messages[-count:]
        lines = ["📱 Recent Telegram messages:"]
        for m in recent:
            lines.append(f"  [{m['from']}]: {m['text'][:80]}")
        return "\n".join(lines)
