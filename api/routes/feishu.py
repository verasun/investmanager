"""FastAPI routes for Feishu webhook."""

import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

from config.settings import settings
from src.feishu.bot import FeishuBot, get_feishu_bot
from src.feishu.client import get_feishu_client


router = APIRouter(prefix="/feishu", tags=["feishu"])


@router.post("/webhook")
async def feishu_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_lark_request_timestamp: str = Header(None),
    x_lark_request_nonce: str = Header(None),
    x_lark_signature: str = Header(None),
) -> JSONResponse:
    """
    Handle Feishu webhook events.

    This endpoint receives events from Feishu when:
    - User sends a message to the bot
    - Bitable data changes
    - Other subscribed events occur
    """
    # Read request body
    body = await request.body()
    body_str = body.decode("utf-8")

    # Log all incoming requests for debugging
    logger.info(f"Feishu webhook received - Headers: {dict(request.headers)}")
    logger.info(f"Feishu webhook body: {body_str[:500]}")

    if not settings.feishu_enabled:
        logger.warning("Feishu integration is disabled")
        raise HTTPException(status_code=403, detail="Feishu integration is disabled")

    try:
        raw_event = json.loads(body_str)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON received: {body_str[:200]}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Handle encrypted request
    event = raw_event
    if "encrypt" in raw_event:
        logger.info("Received encrypted Feishu request, decrypting...")
        client = get_feishu_client()
        try:
            decrypted_json = client.decrypt_event_data(raw_event["encrypt"])
            event = json.loads(decrypted_json)
            logger.info(f"Decrypted event: {event}")
        except Exception as e:
            logger.error(f"Failed to decrypt Feishu event: {e}")
            raise HTTPException(status_code=400, detail="Failed to decrypt event")

    # Handle URL verification challenge (no token verification needed)
    if event.get("type") == "url_verification":
        challenge = event.get("challenge", "")
        logger.info(f"Feishu URL verification: {challenge}")
        return JSONResponse(content={"challenge": challenge})

    # Verify token for regular events
    verification_token = event.get("token") or event.get("header", {}).get("token")
    if settings.feishu_verification_token and verification_token != settings.feishu_verification_token:
        logger.warning(f"Invalid Feishu verification token. Expected: {settings.feishu_verification_token}, Got: {verification_token}")
        raise HTTPException(status_code=401, detail="Invalid verification token")

    # Verify signature (if configured)
    bot = get_feishu_bot()
    if not bot:
        raise HTTPException(status_code=500, detail="Feishu bot not initialized")

    if settings.feishu_encrypt_key and all([
        x_lark_request_timestamp,
        x_lark_request_nonce,
        x_lark_signature,
    ]):
        client = bot._client
        if not client.verify_event_signature(
            x_lark_request_timestamp,
            x_lark_request_nonce,
            body_str,
            x_lark_signature,
        ):
            logger.warning("Invalid Feishu webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Process event in background
    background_tasks.add_task(process_feishu_event, event, bot)

    return JSONResponse(content={"status": "ok"})


async def process_feishu_event(event: dict, bot: FeishuBot) -> None:
    """Process Feishu event in background."""
    try:
        await bot.handle_event(event)
    except Exception as e:
        logger.error(f"Error processing Feishu event: {e}")


@router.get("/status")
async def feishu_status() -> dict[str, Any]:
    """
    Get Feishu integration status.

    Returns:
        Status information
    """
    return {
        "enabled": settings.feishu_enabled,
        "app_id_configured": bool(settings.feishu_app_id),
        "encrypt_key_configured": bool(settings.feishu_encrypt_key),
        "verification_token_configured": bool(settings.feishu_verification_token),
        "bitable_configured": bool(settings.feishu_bitable_token),
        "folder_configured": bool(settings.feishu_folder_token),
    }


@router.post("/test")
async def test_feishu_message(
    chat_id: str = Body(..., embed=True),
    message: str = Body("Test message from InvestManager", embed=True),
) -> dict[str, Any]:
    """
    Send a test message to a Feishu chat.

    This endpoint is for testing purposes only.

    Args:
        chat_id: Target chat ID
        message: Message to send

    Returns:
        Result of the operation
    """
    if not settings.feishu_enabled:
        raise HTTPException(status_code=403, detail="Feishu integration is disabled")

    bot = get_feishu_bot()
    if not bot:
        raise HTTPException(status_code=500, detail="Feishu bot not initialized")

    try:
        result = await bot._client.send_text_message(chat_id, "chat_id", message)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Failed to send test message: {e}")
        return {"success": False, "error": str(e)}