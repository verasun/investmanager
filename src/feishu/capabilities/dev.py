"""Dev capability for development mode with Claude Code integration."""

import asyncio
import os
from typing import Optional

from loguru import logger

from config.settings import settings
from src.feishu.capabilities.base import Capability, CapabilityResult
from src.feishu.gateway.message_router import MessageContext


class DevCapability(Capability):
    """Capability for development mode.

    Handles:
    - Code-related questions via Claude Code
    - Development assistance
    - Remote coding help
    """

    @property
    def name(self) -> str:
        return "dev"

    @property
    def description(self) -> str:
        return "开发模式 - 通过 Claude Code 协助开发和调试"

    async def handle(self, context: MessageContext) -> CapabilityResult:
        """Handle development message via Claude Code.

        Uses Claude CLI subprocess to process development queries.
        """
        user_id = context.user_id
        text = context.raw_text

        logger.info(f"DevCapability handling message from {user_id}: {text[:50]}...")

        # Check if Claude Code is enabled
        if not settings.claude_code_enabled:
            return CapabilityResult(
                success=False,
                message="开发模式未启用。请在配置中设置 CLAUDE_CODE_ENABLED=true",
            )

        # Execute via Claude Code
        try:
            result = await self._execute_claude_code(text)
            return CapabilityResult(
                success=True,
                message=result,
                data={"type": "claude_code_response"},
            )
        except Exception as e:
            logger.error(f"DevCapability error: {e}")
            return CapabilityResult(
                success=False,
                message=f"Claude Code 执行失败: {str(e)}",
            )

    async def _execute_claude_code(self, prompt: str) -> str:
        """Execute Claude Code CLI with the given prompt.

        Args:
            prompt: User's prompt to send to Claude Code

        Returns:
            Claude Code output
        """
        # Determine working directory
        work_dir = settings.claude_code_working_dir or os.getcwd()

        logger.info(f"Executing Claude Code in {work_dir}")

        # Run Claude CLI with --print flag for non-interactive mode
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--print",
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error(f"Claude Code error: {error_msg}")
            raise RuntimeError(f"Claude Code failed: {error_msg}")

        result = stdout.decode()
        logger.info(f"Claude Code output: {result[:200]}...")

        return result


# Global instance
_dev_capability: Optional[DevCapability] = None


def get_dev_capability() -> DevCapability:
    """Get or create the global DevCapability instance."""
    global _dev_capability
    if _dev_capability is None:
        _dev_capability = DevCapability()
    return _dev_capability