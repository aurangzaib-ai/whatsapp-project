"""
WhatsApp Cloud API client (sync requests)

IMPORTANT:
- access_token + phone_number_id are provided per call (from Streamlit UI)
- backend must NOT store token
"""

from __future__ import annotations

import requests
from typing import Any, Dict, Optional, List


class WhatsAppCloudClient:
    def __init__(self, access_token: str, phone_number_id: str, api_version: str = "v19.0"):
        if not access_token:
            raise ValueError("access_token is required")
        if not phone_number_id:
            raise ValueError("phone_number_id is required")

        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

    def send_template_message_sync(
        self,
        recipient_phone: str,
        template_name: str,
        language_code: str = "en_US",
        template_params: Optional[List[str]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Send a template message.

        template_params:
          If provided, they are placed into BODY parameters in order.
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": recipient_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }

        if template_params:
            payload["template"]["components"] = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(p)} for p in template_params],
                }
            ]

        try:
            resp = requests.post(self.base_url, headers=headers, json=payload, timeout=timeout)
            data = resp.json() if resp.content else {}

            if resp.status_code >= 400:
                return {
                    "success": False,
                    "error": data or {"status_code": resp.status_code, "text": resp.text},
                }

            # success: {"messages":[{"id":"wamid..."}]}
            msg_id = None
            if isinstance(data, dict):
                msgs = data.get("messages")
                if isinstance(msgs, list) and msgs:
                    msg_id = msgs[0].get("id")

            return {"success": True, "message_id": msg_id, "raw": data}

        except Exception as e:
            return {"success": False, "error": str(e)}


def get_whatsapp_client(access_token: str, phone_number_id: str) -> WhatsAppCloudClient:
    return WhatsAppCloudClient(access_token=access_token, phone_number_id=phone_number_id)
