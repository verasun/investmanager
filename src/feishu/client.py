"""Feishu (Lark) API client."""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from Crypto.Cipher import AES
from loguru import logger

from config.settings import settings


@dataclass
class FeishuConfig:
    """Feishu app configuration."""

    app_id: str
    app_secret: str
    encrypt_key: str = ""
    verification_token: str = ""


class FeishuClient:
    """
    Feishu Open Platform API client.

    Provides methods for messaging, documents, and bitable operations.
    """

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        encrypt_key: Optional[str] = None,
        verification_token: Optional[str] = None,
    ):
        """
        Initialize Feishu client.

        Args:
            app_id: Feishu app ID
            app_secret: Feishu app secret
            encrypt_key: Encryption key for event decryption
            verification_token: Token for event verification
        """
        self._config = FeishuConfig(
            app_id=app_id or settings.feishu_app_id,
            app_secret=app_secret or settings.feishu_app_secret,
            encrypt_key=encrypt_key or settings.feishu_encrypt_key,
            verification_token=verification_token or settings.feishu_verification_token,
        )
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    async def _get_headers(self) -> dict[str, str]:
        """Get request headers with access token."""
        token = await self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def get_access_token(self) -> str:
        """
        Get tenant access token, refreshing if necessary.

        Returns:
            Valid access token
        """
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        data = {
            "app_id": self._config.app_id,
            "app_secret": self._config.app_secret,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data)
            response.raise_for_status()
            result = response.json()

        if result.get("code") != 0:
            raise Exception(f"Failed to get access token: {result}")

        self._access_token = result["tenant_access_token"]
        self._token_expires_at = time.time() + result.get("expire", 7200) - 300

        logger.info("Feishu access token obtained")
        return self._access_token

    # ==================== Message API ====================

    async def send_text_message(
        self,
        receive_id: str,
        receive_id_type: str,
        text: str,
    ) -> dict:
        """
        Send text message.

        Args:
            receive_id: Receiver ID (user_id, open_id, chat_id, etc.)
            receive_id_type: Type of receive_id (open_id, user_id, chat_id)
            text: Text content

        Returns:
            API response
        """
        url = f"{self.BASE_URL}/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        data = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                params=params,
                headers=await self._get_headers(),
                json=data,
            )
            response.raise_for_status()
            return response.json()

    async def send_card_message(
        self,
        receive_id: str,
        receive_id_type: str,
        card: dict,
    ) -> dict:
        """
        Send interactive card message.

        Args:
            receive_id: Receiver ID
            receive_id_type: Type of receive_id
            card: Card content dict

        Returns:
            API response
        """
        url = f"{self.BASE_URL}/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        data = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                params=params,
                headers=await self._get_headers(),
                json=data,
            )
            response.raise_for_status()
            return response.json()

    async def send_markdown_message(
        self,
        receive_id: str,
        receive_id_type: str,
        title: str,
        content: str,
    ) -> dict:
        """
        Send markdown message.

        Args:
            receive_id: Receiver ID
            receive_id_type: Type of receive_id
            title: Message title
            content: Markdown content

        Returns:
            API response
        """
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": content,
                }
            ],
        }
        return await self.send_card_message(receive_id, receive_id_type, card)

    async def reply_message(
        self,
        message_id: str,
        content: str,
        msg_type: str = "text",
    ) -> dict:
        """
        Reply to a message.

        Args:
            message_id: Message ID to reply to
            content: Message content (string for text, dict for other types)
            msg_type: Message type

        Returns:
            API response
        """
        url = f"{self.BASE_URL}/im/v1/messages/{message_id}/reply"
        data = {
            "msg_type": msg_type,
            "content": json.dumps(
                {"text": content} if msg_type == "text" else content
            ),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=await self._get_headers(),
                json=data,
            )
            if response.status_code != 200:
                logger.error(f"Reply message failed: status={response.status_code}, body={response.text}")
            response.raise_for_status()
            return response.json()

    # ==================== Document API ====================

    async def create_document(
        self,
        title: str,
        folder_token: Optional[str] = None,
    ) -> dict:
        """
        Create a new Feishu document.

        Args:
            title: Document title
            folder_token: Parent folder token

        Returns:
            API response with document info
        """
        url = f"{self.BASE_URL}/docx/v1/documents"
        data = {"title": title}
        if folder_token:
            data["folder_token"] = folder_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=await self._get_headers(),
                json=data,
            )
            response.raise_for_status()
            return response.json()

    async def get_document(self, document_id: str) -> dict:
        """
        Get document info.

        Args:
            document_id: Document ID

        Returns:
            Document info
        """
        url = f"{self.BASE_URL}/docx/v1/documents/{document_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=await self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def create_document_block(
        self,
        document_id: str,
        block_id: str,
        content: dict,
    ) -> dict:
        """
        Add content block to document.

        Args:
            document_id: Document ID
            block_id: Parent block ID (use document_id for root)
            content: Block content

        Returns:
            API response
        """
        url = f"{self.BASE_URL}/docx/v1/documents/{document_id}/blocks/{block_id}/children/batch_create"
        data = {
            "children": [content],
            "index": 0,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=await self._get_headers(),
                json=data,
            )
            response.raise_for_status()
            return response.json()

    # ==================== Bitable (Multi-dimensional Table) API ====================

    async def get_bitable(self, app_token: str) -> dict:
        """
        Get bitable info.

        Args:
            app_token: Bitable app token

        Returns:
            Bitable info
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=await self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def get_bitable_tables(self, app_token: str) -> dict:
        """
        Get tables in a bitable.

        Args:
            app_token: Bitable app token

        Returns:
            List of tables
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=await self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def get_bitable_records(
        self,
        app_token: str,
        table_id: str,
        view_id: Optional[str] = None,
        page_size: int = 100,
    ) -> dict:
        """
        Get records from bitable table.

        Args:
            app_token: Bitable app token
            table_id: Table ID
            view_id: View ID (optional)
            page_size: Page size

        Returns:
            Records
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        params = {"page_size": page_size}
        if view_id:
            params["view_id"] = view_id

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params=params,
                headers=await self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def create_bitable_record(
        self,
        app_token: str,
        table_id: str,
        fields: dict,
    ) -> dict:
        """
        Create a new record in bitable.

        Args:
            app_token: Bitable app token
            table_id: Table ID
            fields: Field values

        Returns:
            Created record
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        data = {"fields": fields}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=await self._get_headers(),
                json=data,
            )
            response.raise_for_status()
            return response.json()

    # ==================== File Upload API ====================

    async def upload_file(
        self,
        file_path: str,
        file_name: str,
        parent_type: str = "ccm_import_open",
        parent_node: Optional[str] = None,
    ) -> dict:
        """
        Upload file to Feishu.

        Args:
            file_path: Local file path
            file_name: File name
            parent_type: Parent type (ccm_import_open, bitable_file, etc.)
            parent_node: Parent node (folder token, etc.)

        Returns:
            Upload result with file token
        """
        url = f"{self.BASE_URL}/drive/v1/medias/upload_all"
        params = {
            "file_name": file_name,
            "parent_type": parent_type,
        }
        if parent_node:
            params["parent_node"] = parent_node

        async with httpx.AsyncClient() as client:
            with open(file_path, "rb") as f:
                files = {"file": (file_name, f)}
                response = await client.post(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {await self.get_access_token()}"},
                    files=files,
                )
                response.raise_for_status()
                return response.json()

    # ==================== Event Verification ====================

    def verify_event_signature(
        self,
        timestamp: str,
        nonce: str,
        body: str,
        signature: str,
    ) -> bool:
        """
        Verify event signature.

        Args:
            timestamp: Request timestamp
            nonce: Request nonce
            body: Request body
            signature: Signature to verify

        Returns:
            True if valid
        """
        if not self._config.encrypt_key:
            return True  # Skip verification if no key configured

        sign_base = f"{timestamp}{nonce}{self._config.encrypt_key}{body}"
        expected_sig = hashlib.sha256(sign_base.encode()).hexdigest()
        return hmac.compare_digest(signature, expected_sig)

    def decrypt_event_data(self, encrypted_data: str) -> str:
        """
        Decrypt encrypted event data.

        Args:
            encrypted_data: Base64 encoded encrypted data

        Returns:
            Decrypted JSON string
        """
        if not self._config.encrypt_key:
            return encrypted_data

        key = hashlib.sha256(self._config.encrypt_key.encode()).digest()
        encrypted_bytes = base64.b64decode(encrypted_data)

        cipher = AES.new(key, AES.MODE_CBC, iv=encrypted_bytes[:16])
        decrypted = cipher.decrypt(encrypted_bytes[16:])

        # Remove PKCS7 padding
        padding_len = decrypted[-1]
        return decrypted[:-padding_len].decode()


# Global client instance
_feishu_client: Optional[FeishuClient] = None


def get_feishu_client() -> FeishuClient:
    """Get or create the global Feishu client instance."""
    global _feishu_client
    if _feishu_client is None and settings.feishu_enabled:
        _feishu_client = FeishuClient()
        logger.info("Feishu client initialized")
    return _feishu_client