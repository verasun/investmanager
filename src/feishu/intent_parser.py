"""Intelligent command parser using LLM with personalization."""

import json
from typing import Any, Optional

from loguru import logger

from config.settings import settings


# Web search tool definition for LLM function calling
WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "搜索互联网获取最新信息。当用户询问时事新闻、最新数据、实时信息、当前事件或需要最新资料时使用此工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，应该是简洁、准确的搜索词"
                }
            },
            "required": ["query"]
        }
    }
}


class IntentParser:
    """Parse natural language commands using LLM with personalization support."""

    SYSTEM_PROMPT = """你是一个股票分析机器人的指令解析器。分析用户消息，提取用户意图和参数。

支持的意图类型：
- collect_data: 收集股票数据
- analyze: 单独分析股票（仅技术分析）
- backtest: 单独策略回测
- comprehensive: 组合指令，串行执行完整分析流程（数据获取→技术分析→策略回测→综合报告）
- mode_switch: 切换工作模式
- mode_status: 查询当前模式
- report: 生成报告
- status: 查询任务状态
- help: 获取帮助
- unknown: 无法识别

请以JSON格式返回：
{
  "intent": "意图类型",
  "params": {
    "symbols": ["股票代码列表"],
    "strategy": "策略名",
    "days": 天数数字,
    "report_type": "报告类型"
  },
  "confidence": 0.0-1.0的置信度,
  "explanation": "简短解释"
}

注意：
1. 股票代码通常是6位数字，如600519、000001，必须放入symbols数组中
2. 策略名可能是：ma、均线、momentum、macd等
3. 天数可能是：一年、2年、365天等表达
4. 如果意图不明确，设置confidence较低
5. 只返回JSON，不要其他内容
6. "综合分析"、"完整分析"、"深度评估"等关键词应识别为comprehensive意图"""

    DEFAULT_CHAT_PROMPT = "你是一个友好的投资助手。对于股票相关问题，请给出专业建议；对于其他问题，请友好回复。回复要简洁，不超过200字。"

    def __init__(self):
        """Initialize intent parser."""
        self._client = None
        self._enabled = self._check_llm_available()
        self._memory_modules_loaded = False
        self._web_search_modules_loaded = False

    def _load_web_search_modules(self):
        """Lazily load web search modules."""
        if self._web_search_modules_loaded:
            return

        try:
            from src.web import WebSearcher, SearchIntentDetector, SearchEngine
            from src.web.search import get_web_searcher
            from src.web.intent_detector import get_intent_detector

            self._web_searcher = get_web_searcher()
            self._intent_detector = get_intent_detector()
            self._search_engine = SearchEngine
            self._web_search_modules_loaded = True
        except Exception as e:
            logger.warning(f"Failed to load web search modules: {e}")
            self._web_search_modules_loaded = False

    def _load_memory_modules(self):
        """Lazily load memory modules to avoid circular imports."""
        if self._memory_modules_loaded:
            return

        try:
            from src.memory import (
                get_profile_manager,
                get_conversation_memory,
                get_preference_extractor,
                get_prompt_builder,
                get_learning_manager,
            )
            self._profile_manager = get_profile_manager()
            self._conversation_memory = get_conversation_memory()
            self._preference_extractor = get_preference_extractor()
            self._prompt_builder = get_prompt_builder()
            self._learning_manager = get_learning_manager()
            self._memory_modules_loaded = True
        except Exception as e:
            logger.warning(f"Failed to load memory modules: {e}")
            self._memory_modules_loaded = False

    def _check_llm_available(self) -> bool:
        """Check if LLM is configured."""
        return bool(
            settings.openai_api_key
            or settings.anthropic_api_key
            or settings.alibaba_bailian_api_key
        )

    async def chat(
        self,
        user_message: str,
        unrestricted: bool = False,
        user_id: Optional[str] = None,
    ) -> str:
        """Chat with LLM for general questions with personalization.

        Args:
            user_message: User's message
            unrestricted: If True, use general chat mode (no investment-focused system prompt)
            user_id: Optional user ID for personalization

        Returns:
            LLM response string
        """
        if not self._enabled:
            return "抱歉，我暂时无法回答这个问题。请稍后再试。"

        logger.info(f"LLM chat request (unrestricted={unrestricted}, user={user_id}): {user_message[:50]}...")

        # Get personalized prompt if user_id provided
        system_prompt = None
        learning_task_info = None

        # Personalization should happen regardless of unrestricted flag
        # unrestricted only controls the type of system prompt
        if user_id:
            self._load_memory_modules()
            if self._memory_modules_loaded:
                try:
                    # Get user profile
                    profile = await self._profile_manager.get(user_id)

                    # Check for pending learning task
                    pending_task = await self._learning_manager.get_pending_task_for_user(user_id)
                    if pending_task:
                        learning_task_info = pending_task

                    # Build personalized system prompt based on mode
                    if not unrestricted:
                        # Investment-focused mode
                        system_prompt = await self._prompt_builder.build_system_prompt(
                            profile,
                            include_history=True,
                            learning_task=f"请询问用户：{pending_task['question']}" if pending_task else None,
                        )
                    else:
                        # General chat mode - use profile for personalization
                        system_prompt = self._prompt_builder.build_chat_prompt(
                            profile,
                            is_unrestricted=True,
                        )

                    # Record message and update profile
                    await self._conversation_memory.add_message(
                        user_id, "user", user_message
                    )

                    # Extract preferences from message
                    extracted = self._preference_extractor.extract(user_message)
                    if extracted.has_preferences() or extracted.mentioned_stocks:
                        await self._conversation_memory.add_message(
                            user_id, "user", user_message,
                            preferences_extracted=extracted.to_dict()
                        )

                        # Update stock mentions
                        for stock in extracted.mentioned_stocks:
                            await self._profile_manager.add_stock_mention(user_id, stock)

                    # Increment interaction count
                    await self._profile_manager.increment_interactions(user_id)

                except Exception as e:
                    logger.warning(f"Failed to get personalized prompt: {e}")
                    if not unrestricted:
                        system_prompt = self.DEFAULT_CHAT_PROMPT

        # Fallback for no user_id
        if system_prompt is None and not unrestricted:
            system_prompt = self.DEFAULT_CHAT_PROMPT

        # Try web search with tool calling if enabled
        if settings.web_search_enabled:
            self._load_web_search_modules()
            if self._web_search_modules_loaded:
                result = await self._chat_with_web_search(
                    user_message, system_prompt, unrestricted
                )
                if result:
                    # Record assistant response
                    if user_id and self._memory_modules_loaded:
                        try:
                            await self._conversation_memory.add_message(
                                user_id, "assistant", result
                            )
                        except Exception as e:
                            logger.warning(f"Failed to record assistant message: {e}")

                    # Append learning task options if applicable
                    if learning_task_info:
                        options_text = "\n".join(
                            f"{i+1}. {opt}" for i, opt in enumerate(learning_task_info["options"])
                        )
                        result = f"{result}\n\n{learning_task_info['question']}\n{options_text}"

                    logger.info(f"LLM chat response (with web search): {result[:100]}...")
                    return result

        # Standard LLM call without web search
        result = await self._get_llm_response(
            user_message,
            chat_mode=True,
            unrestricted=unrestricted,
            system_prompt=system_prompt,
        )

        if not result:
            return "抱歉，我暂时无法回答这个问题。请稍后再试。"

        # Record assistant response
        if user_id and self._memory_modules_loaded:
            try:
                await self._conversation_memory.add_message(
                    user_id, "assistant", result
                )
            except Exception as e:
                logger.warning(f"Failed to record assistant message: {e}")

        # Append learning task options if applicable
        if learning_task_info:
            options_text = "\n".join(
                f"{i+1}. {opt}" for i, opt in enumerate(learning_task_info["options"])
            )
            result = f"{result}\n\n{learning_task_info['question']}\n{options_text}"

        logger.info(f"LLM chat response: {result[:100]}...")
        return result

    async def _chat_with_web_search(
        self,
        user_message: str,
        system_prompt: Optional[str],
        unrestricted: bool,
    ) -> Optional[str]:
        """Chat with LLM using web search tool calling.

        Args:
            user_message: User's message
            system_prompt: System prompt to use
            unrestricted: Whether in unrestricted mode

        Returns:
            LLM response string or None if tool calling not supported
        """
        provider = settings.llm_provider

        try:
            # Try OpenAI-compatible tool calling (works for OpenAI and Alibaba Bailian)
            if settings.alibaba_bailian_api_key and provider == "alibaba_bailian":
                return await self._call_with_tools_alibaba_bailian(
                    user_message, system_prompt, unrestricted
                )
            elif settings.openai_api_key and provider == "openai":
                return await self._call_with_tools_openai(
                    user_message, system_prompt, unrestricted
                )
            # Fallback: keyword-based search detection
            elif self._intent_detector.needs_search(user_message):
                logger.info(f"Using keyword-based search for: {user_message[:50]}")
                intent = self._intent_detector.detect(user_message)
                search_query = intent.query or user_message

                # Execute search
                engine = self._search_engine(settings.web_search_engine)
                search_response = await self._web_searcher.search(search_query, engine)

                if not search_response.error:
                    # Enrich message with search results
                    search_context = self._web_searcher.format_results_for_llm(search_response)
                    enriched_message = f"{user_message}\n\n[搜索结果]\n{search_context}"

                    # Get LLM response with search context
                    return await self._get_llm_response(
                        enriched_message,
                        chat_mode=True,
                        unrestricted=unrestricted,
                        system_prompt=system_prompt,
                    )

            return None

        except Exception as e:
            logger.error(f"Web search tool calling failed: {e}")
            return None

    async def _call_with_tools_openai(
        self,
        user_message: str,
        system_prompt: Optional[str],
        unrestricted: bool,
    ) -> Optional[str]:
        """Call OpenAI with web search tool."""
        import openai

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

        messages = []
        if not unrestricted and system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        model = getattr(settings, 'openai_model', 'gpt-3.5-turbo') or 'gpt-3.5-turbo'

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[WEB_SEARCH_TOOL],
            tool_choice="auto",
            temperature=0.7,
            max_tokens=800,
        )

        message = response.choices[0].message

        # Handle tool call
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name == "web_search":
                    args = json.loads(tool_call.function.arguments)
                    query = args.get("query", user_message)

                    logger.info(f"OpenAI requested web search: {query}")

                    # Execute search
                    engine = self._search_engine(settings.web_search_engine)
                    search_result = await self._web_searcher.search(query, engine)
                    search_context = self._web_searcher.format_results_for_llm(search_result)

                    # Continue conversation with search results
                    messages.append(message)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": search_context,
                    })

                    # Get final response
                    final_response = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=800,
                    )
                    return final_response.choices[0].message.content

        return message.content

    async def _call_with_tools_alibaba_bailian(
        self,
        user_message: str,
        system_prompt: Optional[str],
        unrestricted: bool,
    ) -> Optional[str]:
        """Call Alibaba Bailian (Qwen) with web search tool.

        Qwen models support OpenAI-compatible function calling.
        """
        import openai

        model = settings.alibaba_bailian_model or 'qwen-turbo'

        client = openai.AsyncOpenAI(
            api_key=settings.alibaba_bailian_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        messages = []
        if not unrestricted and system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=[WEB_SEARCH_TOOL],
                tool_choice="auto",
                temperature=0.7,
                max_tokens=800,
            )
        except Exception as e:
            # Some Qwen models may not support tools, fallback to keyword-based
            logger.warning(f"Alibaba Bailian tool calling failed: {e}, using keyword-based fallback")
            return None

        message = response.choices[0].message

        # Handle tool call
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name == "web_search":
                    args = json.loads(tool_call.function.arguments)
                    query = args.get("query", user_message)

                    logger.info(f"Alibaba Bailian requested web search: {query}")

                    # Execute search
                    engine = self._search_engine(settings.web_search_engine)
                    search_result = await self._web_searcher.search(query, engine)
                    search_context = self._web_searcher.format_results_for_llm(search_result)

                    # Continue conversation with search results
                    messages.append(message)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": search_context,
                    })

                    # Get final response
                    final_response = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=800,
                    )
                    return final_response.choices[0].message.content

        return message.content

    async def handle_learning_response(
        self,
        user_id: str,
        message: str,
    ) -> Optional[dict]:
        """Handle response to a learning task.

        Args:
            user_id: User ID
            message: User's response message

        Returns:
            Dict with result info if this was a learning response, None otherwise
        """
        self._load_memory_modules()
        if not self._memory_modules_loaded:
            return None

        try:
            # Check if user is responding to a learning task
            # Get the last asked task
            import aiosqlite
            from config.settings import settings as cfg

            db_path = cfg.sqlite_db_path or "./data/investmanager.db"

            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    """
                    SELECT * FROM learning_tasks
                    WHERE user_id = ? AND asked = 1 AND answered = 0
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_id,),
                )
                row = await cursor.fetchone()

                if not row:
                    return None

                task_id = row["task_id"]
                options = json.loads(row["options"])

            # Check if message is an option selection
            option_idx = self._preference_extractor.detect_option_selection(
                message, options
            )

            if option_idx is not None:
                # Complete the task
                preference_value = await self._learning_manager.complete_task(
                    task_id, message, option_idx
                )
                return {
                    "type": "learning_response",
                    "task_id": task_id,
                    "preference_set": preference_value,
                    "message": f"好的，已记录您的偏好！",
                }

            return None

        except Exception as e:
            logger.warning(f"Failed to handle learning response: {e}")
            return None

    async def _get_llm_response(
        self,
        user_message: str,
        chat_mode: bool = False,
        unrestricted: bool = False,
        system_prompt: Optional[str] = None,
    ) -> Optional[dict | str]:
        """Get LLM response for intent parsing or chat."""
        try:
            provider = getattr(settings, 'llm_provider', 'openai')

            # Prepare system prompt
            if system_prompt is None and not unrestricted:
                system_prompt = self.DEFAULT_CHAT_PROMPT if chat_mode else self.SYSTEM_PROMPT

            # Try Alibaba Bailian first if configured
            if settings.alibaba_bailian_api_key and provider == "alibaba_bailian":
                return await self._call_alibaba_bailian(user_message, chat_mode, unrestricted, system_prompt)
            elif settings.openai_api_key and provider == "openai":
                return await self._call_openai(user_message, chat_mode, unrestricted, system_prompt)
            elif settings.anthropic_api_key and provider == "anthropic":
                return await self._call_anthropic(user_message, chat_mode, unrestricted, system_prompt)
            # Fallback: try any available provider
            elif settings.alibaba_bailian_api_key:
                return await self._call_alibaba_bailian(user_message, chat_mode, unrestricted, system_prompt)
            elif settings.openai_api_key:
                return await self._call_openai(user_message, chat_mode, unrestricted, system_prompt)
            elif settings.anthropic_api_key:
                return await self._call_anthropic(user_message, chat_mode, unrestricted, system_prompt)
            else:
                return None
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    async def _call_openai(
        self,
        user_message: str,
        chat_mode: bool = False,
        unrestricted: bool = False,
        system_prompt: Optional[str] = None,
    ) -> Optional[dict | str]:
        """Call OpenAI API."""
        import openai

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

        messages = [{"role": "user", "content": user_message}]
        if not unrestricted and system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        response = await client.chat.completions.create(
            model=getattr(settings, 'openai_model', 'gpt-3.5-turbo'),
            messages=messages,
            temperature=0.7 if chat_mode else 0,
            max_tokens=800,
        )

        content = response.choices[0].message.content
        if chat_mode:
            return content
        return self._parse_json_response(content)

    async def _call_anthropic(
        self,
        user_message: str,
        chat_mode: bool = False,
        unrestricted: bool = False,
        system_prompt: Optional[str] = None,
    ) -> Optional[dict | str]:
        """Call Anthropic API."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        system = None if unrestricted else system_prompt

        response = await client.messages.create(
            model=getattr(settings, 'anthropic_model', 'claude-3-haiku-20240307'),
            max_tokens=800,
            system=system,
            messages=[
                {"role": "user", "content": user_message},
            ],
        )

        content = response.content[0].text
        if chat_mode:
            return content
        return self._parse_json_response(content)

    async def _call_alibaba_bailian(
        self,
        user_message: str,
        chat_mode: bool = False,
        unrestricted: bool = False,
        system_prompt: Optional[str] = None,
    ) -> Optional[dict | str]:
        """Call Alibaba Bailian (DashScope) API.

        Supports Qwen models through OpenAI-compatible API.
        API Base: https://dashscope.aliyuncs.com/compatible-mode/v1
        """
        import openai

        model = getattr(settings, 'alibaba_bailian_model', 'qwen-turbo') or 'qwen-turbo'

        client = openai.AsyncOpenAI(
            api_key=settings.alibaba_bailian_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        messages = [{"role": "user", "content": user_message}]
        if not unrestricted and system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7 if chat_mode else 0,
            max_tokens=800,
        )

        content = response.choices[0].message.content
        if chat_mode:
            return content
        return self._parse_json_response(content)

    def _parse_json_response(self, content: str) -> Optional[dict]:
        """Parse JSON from LLM response."""
        try:
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return None

    async def parse(self, text: str) -> tuple[str, dict[str, Any], float]:
        """
        Parse user message to extract intent and parameters.

        Args:
            text: User message text

        Returns:
            Tuple of (intent, params, confidence)
        """
        if not self._enabled:
            return "unknown", {}, 0.0

        result = await self._get_llm_response(text, chat_mode=False)

        if not result or isinstance(result, str):
            return "unknown", {}, 0.0

        intent = result.get("intent", "unknown")
        params = result.get("params", {})
        confidence = result.get("confidence", 0.0)

        logger.info(f"LLM parsed intent: {intent}, params: {params}, confidence: {confidence}")

        return intent, params, confidence


# Global instance
_intent_parser: Optional[IntentParser] = None


def get_intent_parser() -> IntentParser:
    """Get or create intent parser instance."""
    global _intent_parser
    if _intent_parser is None:
        _intent_parser = IntentParser()
    return _intent_parser