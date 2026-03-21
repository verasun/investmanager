"""Intent Router - LLM-based intent parsing and service routing.

This module provides:
- LLM-based intent parsing
- Capability-aware routing decisions
- Parameter extraction from user messages

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                         GATEWAY (:8000)                             │
│  ┌─────────────────┐                                                │
│  │  Registry       │◀────┐                                          │
│  │  Manager        │     │                                          │
│  └─────────────────┘     │ Get capabilities                         │
│                          │                                          │
│  ┌───────────────────────┴───────────────────────────────────────┐ │
│  │                      Intent Router                             │ │
│  │  1. Build capability description prompt                        │ │
│  │  2. Call LLM to parse user intent                              │ │
│  │  3. Match intent to service                                    │ │
│  │  4. Extract parameters                                         │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                          │                                          │
│                          ▼                                          │
│                   Route to Service                                  │
└─────────────────────────────────────────────────────────────────────┘
"""

import json
import re
from typing import Any, Optional

import httpx
from loguru import logger

from services.capability_protocol import (
    CapabilityInfo,
    IntentParseRequest,
    IntentParseResponse,
)


# ============================================
# Intent Router
# ============================================

class IntentRouter:
    """Routes user messages to appropriate services using LLM-based intent parsing."""

    # Intent parsing system prompt
    INTENT_SYSTEM_PROMPT = """你是InvestManager的路由器。根据用户消息，选择最合适的服务处理。

## 输出格式
请严格按照以下JSON格式输出，不要包含任何其他内容：
```json
{{
  "service": "服务ID",
  "confidence": 0.0-1.0,
  "endpoint": "/端点路径",
  "parameters": {{}},
  "reasoning": "选择理由"
}}
```

## 选择规则
1. confidence（置信度）范围：0.0-1.0，表示对选择的确定程度
2. 如果无法确定，选择 "chat" 服务，confidence 设为 0.3
3. 如果用户明确要求使用某个模块，优先满足用户要求

## 可用服务：
{services_description}

## 用户消息
{user_message}

请输出JSON格式的路由决策："""

    # Fallback routing keywords
    ROUTING_KEYWORDS = {
        "invest": [
            "股票", "分析", "投资", "回测", "报告", "技术指标", "均线",
            "K线", "基本面", "财务", "涨跌", "股价", "买卖", "持仓",
            "收益", "风险", "组合", "量化", "策略", "指数", "基金",
        ],
        "chat": [
            "聊天", "天气", "新闻", "搜索", "查询", "帮助", "什么",
            "怎么", "为什么", "如何", "谁", "哪里", "什么时候",
        ],
        "dev": [
            "代码", "开发", "调试", "bug", "功能", "实现", "重构",
            "测试", "写代码", "编程", "运行", "执行", "修复",
        ],
    }

    def __init__(self, llm_url: str = "http://localhost:8001"):
        """Initialize intent router.

        Args:
            llm_url: URL of the LLM service
        """
        self._llm_url = llm_url.rstrip("/")
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def parse_intent(
        self,
        request: IntentParseRequest,
        capabilities: dict[str, CapabilityInfo],
    ) -> IntentParseResponse:
        """Parse user intent and determine routing.

        Args:
            request: Intent parse request with user message
            capabilities: Available capabilities from registry

        Returns:
            Intent parse response with routing decision
        """
        # If forced service is specified, use it directly
        if request.force_service:
            service_id = request.force_service
            if service_id in capabilities:
                return IntentParseResponse(
                    service_id=service_id,
                    confidence=1.0,
                    endpoint="/handle",
                    parameters={},
                    reasoning="User forced mode",
                )

        # Build capability description
        services_desc = self._build_capability_description(capabilities)

        # Build system prompt
        system_prompt = self.INTENT_SYSTEM_PROMPT.format(
            services_description=services_desc,
            user_message=request.user_message,
        )

        # Try LLM-based parsing first
        try:
            response = await self._call_llm(system_prompt, request.user_message)
            if response:
                return response
        except Exception as e:
            logger.warning(f"LLM intent parsing failed: {e}, using fallback")

        # Fallback to keyword-based routing
        return self._fallback_routing(request.user_message, capabilities)

    def _build_capability_description(
        self,
        capabilities: dict[str, CapabilityInfo],
    ) -> str:
        """Build a description of available capabilities for LLM prompt.

        Args:
            capabilities: Available capabilities

        Returns:
            Formatted capability description
        """
        if not capabilities:
            return "No services available."

        lines = []

        for service in sorted(
            capabilities.values(),
            key=lambda x: x.priority,
            reverse=True
        ):
            lines.append(f"\n### {service.service_id} ({service.service_name})")
            lines.append(f"描述：{service.description}")

            if service.endpoints:
                lines.append("功能：")
                for endpoint in service.endpoints:
                    lines.append(f"  - {endpoint.description}")
                    if endpoint.tags:
                        lines.append(f"    标签: {', '.join(endpoint.tags[:5])}")

            if service.keywords:
                lines.append(f"关键词: {', '.join(service.keywords[:8])}")

        return "\n".join(lines)

    async def _call_llm(
        self,
        system_prompt: str,
        user_message: str,
    ) -> Optional[IntentParseResponse]:
        """Call LLM for intent parsing.

        Args:
            system_prompt: System prompt with capability descriptions
            user_message: User's message to parse

        Returns:
            Parsed intent response or None if parsing failed
        """
        client = await self._get_client()

        try:
            response = await client.post(
                f"{self._llm_url}/chat",
                json={
                    "messages": [{"role": "user", "content": user_message}],
                    "system_prompt": system_prompt,
                    "temperature": 0.1,  # Low temperature for more deterministic routing
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            data = response.json()

            content = data.get("content", "")
            return self._parse_llm_response(content)

        except httpx.HTTPError as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def _parse_llm_response(self, content: str) -> Optional[IntentParseResponse]:
        """Parse LLM response to extract routing decision.

        Args:
            content: LLM response content

        Returns:
            Parsed intent response or None if parsing failed
        """
        import json

        # Clean up content
        content = content.strip()

        # Try to extract JSON from response
        # First, try parsing the whole content as JSON
        try:
            data = json.loads(content)
            service_id = data.get("service", "chat")
            confidence = float(data.get("confidence", 0.5))
            endpoint = data.get("endpoint", "/handle")
            parameters = data.get("parameters", {})
            reasoning = data.get("reasoning", "")

            return IntentParseResponse(
                service_id=service_id,
                confidence=confidence,
                endpoint=endpoint,
                parameters=parameters,
                reasoning=reasoning,
            )
        except (json.JSONDecodeError, ValueError):
            pass

        # Try to extract JSON from markdown code block
        code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if code_block_match:
            try:
                data = json.loads(code_block_match.group(1))
                service_id = data.get("service", "chat")
                confidence = float(data.get("confidence", 0.5))
                return IntentParseResponse(
                    service_id=service_id,
                    confidence=confidence,
                    endpoint=data.get("endpoint", "/handle"),
                    parameters=data.get("parameters", {}),
                    reasoning=data.get("reasoning", ""),
                )
            except (json.JSONDecodeError, ValueError):
                pass

        # Try to find JSON object with more lenient pattern
        # Match from { to } accounting for nested structures
        json_start = content.find('{')
        if json_start >= 0:
            # Find matching closing brace
            depth = 0
            json_end = -1
            for i in range(json_start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        json_end = i + 1
                        break

            if json_end > json_start:
                json_str = content[json_start:json_end]
                try:
                    data = json.loads(json_str)
                    service_id = data.get("service", "chat")
                    confidence = float(data.get("confidence", 0.5))
                    return IntentParseResponse(
                        service_id=service_id,
                        confidence=confidence,
                        endpoint=data.get("endpoint", "/handle"),
                        parameters=data.get("parameters", {}),
                        reasoning=data.get("reasoning", ""),
                    )
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse LLM response JSON: {e}")

        logger.warning(f"Could not parse intent from LLM response: {content[:100]}")
        return None

    def _fallback_routing(
        self,
        user_message: str,
        capabilities: dict[str, CapabilityInfo],
    ) -> IntentParseResponse:
        """Fallback keyword-based routing.

        Args:
            user_message: User's message
            capabilities: Available capabilities

        Returns:
            Routing decision based on keywords
        """
        message_lower = user_message.lower()
        scores: dict[str, float] = {}

        # Score each service based on keyword matches
        for service_id, keywords in self.ROUTING_KEYWORDS.items():
            if service_id not in capabilities:
                continue

            score = 0.0
            matched_keywords = []

            for keyword in keywords:
                if keyword in message_lower:
                    # Weight by keyword length (longer keywords are more specific)
                    weight = len(keyword) / 10.0
                    score += weight
                    matched_keywords.append(keyword)

            if matched_keywords:
                scores[service_id] = score

        # Select service with highest score
        if scores:
            best_service = max(scores, key=scores.get)
            confidence = min(0.7, scores[best_service] / 3.0)  # Cap at 0.7

            return IntentParseResponse(
                service_id=best_service,
                confidence=confidence,
                endpoint="/handle",
                parameters={},
                reasoning=f"Keyword-based routing (matched keywords)",
            )

        # Default to chat service
        if "chat" in capabilities:
            return IntentParseResponse(
                service_id="chat",
                confidence=0.3,
                endpoint="/handle",
                parameters={},
                reasoning="Default routing (no keywords matched)",
            )

        # If chat is not available, use first available service
        if capabilities:
            first_service = next(iter(capabilities.keys()))
            return IntentParseResponse(
                service_id=first_service,
                confidence=0.3,
                endpoint="/handle",
                parameters={},
                reasoning="Default routing (chat not available)",
            )

        # No services available
        return IntentParseResponse(
            service_id="",
            confidence=0.0,
            reasoning="No services available",
        )

    # ========================================
    # Parameter Extraction
    # ========================================

    def extract_parameters(
        self,
        user_message: str,
        endpoint_info: Any,  # EndpointInfo
    ) -> dict[str, Any]:
        """Extract parameters from user message based on endpoint definition.

        Args:
            user_message: User's message
            endpoint_info: Endpoint information with parameter definitions

        Returns:
            Extracted parameters
        """
        params = {}

        if not hasattr(endpoint_info, 'parameters'):
            return params

        for param in endpoint_info.parameters:
            param_name = param.name
            param_type = param.type

            # Try to extract the parameter value
            value = self._extract_param_value(
                user_message,
                param_name,
                param_type,
            )

            if value is not None:
                params[param_name] = value
            elif param.default is not None:
                params[param_name] = param.default

        return params

    def _extract_param_value(
        self,
        message: str,
        param_name: str,
        param_type: str,
    ) -> Optional[Any]:
        """Extract a single parameter value from message.

        Args:
            message: User's message
            param_name: Parameter name
            param_type: Parameter type

        Returns:
            Extracted value or None
        """
        # Stock code pattern (Chinese A-share or US)
        if param_name in ["symbol", "stock_code", "股票代码"]:
            # Chinese A-share: 6 digits
            match = re.search(r'\b(\d{6})\b', message)
            if match:
                return match.group(1)
            # US stock: 1-5 uppercase letters
            match = re.search(r'\b([A-Z]{1,5})\b', message)
            if match:
                return match.group(1)

        # Days/count pattern
        if param_name in ["days", "count", "天数"]:
            match = re.search(r'(\d+)\s*[天日]', message)
            if match:
                return int(match.group(1))

        # Strategy pattern
        if param_name == "strategy":
            strategy_keywords = {
                "均线": "ma",
                "macd": "macd",
                "rsi": "rsi",
                "布林": "bollinger",
                "动量": "momentum",
            }
            for keyword, strategy in strategy_keywords.items():
                if keyword in message.lower():
                    return strategy

        return None


# ============================================
# Global Instance
# ============================================

_intent_router: Optional[IntentRouter] = None


def get_intent_router() -> IntentRouter:
    """Get or create the global intent router."""
    global _intent_router
    if _intent_router is None:
        _intent_router = IntentRouter()
    return _intent_router