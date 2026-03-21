"""Capability Protocol - Data structures for service registration and discovery.

This module defines the protocol for services to register their capabilities
with the Gateway, enabling dynamic service discovery and intelligent routing.

Architecture:
┌─────────────────┐                    ┌─────────────────┐
│  Invest Service │───┐           ┌───▶│  Capability     │
│    :8010        │   │           │    │  Registry       │
├─────────────────┤   │  REGISTER │    │  (Gateway)      │
│  Chat Service   │───┼──────────▶│    └─────────────────┘
│    :8011        │   │           │           │
├─────────────────┤   │           │           │ ROUTE
│  Dev Service    │───┘           │           ▼
│    :8012        │               │    ┌─────────────────┐
└─────────────────┘               │    │  Intent Router  │
                                  │    │  (LLM-based)    │
                                  │    └─────────────────┘
                                  │
                                  └───▶ Handle requests
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================
# Enums
# ============================================

class ServiceStatus(str, Enum):
    """Service health status."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    UNKNOWN = "unknown"


class ParamType(str, Enum):
    """Parameter type."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


# ============================================
# Parameter Info
# ============================================

class ParamInfo(BaseModel):
    """Parameter information for an endpoint.

    Describes a single parameter that an endpoint accepts.
    """
    name: str = Field(..., description="Parameter name")
    type: str = Field(default="string", description="Parameter type: string, integer, float, boolean, array, object")
    required: bool = Field(default=True, description="Whether this parameter is required")
    description: str = Field(default="", description="Human-readable description of the parameter")
    default: Optional[Any] = Field(default=None, description="Default value if not provided")
    example: Optional[Any] = Field(default=None, description="Example value for documentation")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "symbol",
                "type": "string",
                "required": True,
                "description": "Stock symbol, e.g., '600519' or 'AAPL'",
                "example": "600519"
            }
        }


# ============================================
# Endpoint Info
# ============================================

class EndpointInfo(BaseModel):
    """Endpoint information for a capability.

    Describes a single endpoint (API route) that a service provides.
    """
    path: str = Field(..., description="Endpoint path, e.g., '/analyze'")
    method: str = Field(default="POST", description="HTTP method: GET, POST, PUT, DELETE")
    description: str = Field(default="", description="Human-readable description of what this endpoint does")
    parameters: list[ParamInfo] = Field(default_factory=list, description="List of parameters this endpoint accepts")
    tags: list[str] = Field(default_factory=list, description="Tags for intent matching, e.g., ['股票分析', '技术分析']")
    response_description: Optional[str] = Field(default=None, description="Description of response format")

    class Config:
        json_schema_extra = {
            "example": {
                "path": "/analyze",
                "method": "POST",
                "description": "Analyze a specific stock with technical and fundamental analysis",
                "tags": ["股票分析", "技术分析", "基本面分析"],
                "parameters": [
                    {
                        "name": "symbol",
                        "type": "string",
                        "required": True,
                        "description": "Stock symbol",
                        "example": "600519"
                    },
                    {
                        "name": "days",
                        "type": "integer",
                        "required": False,
                        "description": "Number of days to analyze",
                        "default": 365
                    }
                ]
            }
        }


# ============================================
# Capability Info (Service Registration)
# ============================================

class CapabilityInfo(BaseModel):
    """Capability module registration information.

    This is the main data structure that services use to register
    their capabilities with the Gateway.
    """
    service_id: str = Field(..., description="Unique service identifier, e.g., 'invest', 'chat', 'dev'")
    service_name: str = Field(..., description="Human-readable service name, e.g., '投资分析服务'")
    description: str = Field(default="", description="Detailed description of what this service provides")
    version: str = Field(default="1.0.0", description="Service version")
    base_url: str = Field(..., description="Base URL for the service, e.g., 'http://localhost:8010'")
    endpoints: list[EndpointInfo] = Field(default_factory=list, description="List of endpoints this service provides")
    keywords: list[str] = Field(default_factory=list, description="Keywords for intent matching")
    priority: int = Field(default=0, description="Priority for routing (higher = more preferred)")

    # Runtime state (not part of registration)
    status: ServiceStatus = Field(default=ServiceStatus.UNKNOWN, description="Current service status")
    registered_at: Optional[datetime] = Field(default=None, description="When this service was registered")
    last_heartbeat: Optional[datetime] = Field(default=None, description="Last heartbeat time")

    class Config:
        json_schema_extra = {
            "example": {
                "service_id": "invest",
                "service_name": "投资分析服务",
                "description": "提供股票分析、回测、报告等投资相关功能",
                "version": "1.0.0",
                "base_url": "http://localhost:8010",
                "endpoints": [
                    {
                        "path": "/analyze",
                        "method": "POST",
                        "description": "分析指定股票",
                        "tags": ["股票分析", "技术分析"],
                        "parameters": [
                            {"name": "symbol", "type": "string", "required": True, "description": "股票代码"}
                        ]
                    }
                ],
                "keywords": ["股票", "分析", "投资", "回测", "报告"]
            }
        }


# ============================================
# Registration Messages
# ============================================

class RegisterRequest(BaseModel):
    """Request to register a service with the Gateway."""
    capability: CapabilityInfo


class RegisterResponse(BaseModel):
    """Response to a registration request."""
    success: bool
    message: str
    service_id: Optional[str] = None
    registered_at: Optional[datetime] = None


class UnregisterRequest(BaseModel):
    """Request to unregister a service from the Gateway."""
    service_id: str


class UnregisterResponse(BaseModel):
    """Response to an unregistration request."""
    success: bool
    message: str


class HeartbeatRequest(BaseModel):
    """Heartbeat from a registered service."""
    service_id: str
    status: ServiceStatus = ServiceStatus.HEALTHY
    metrics: Optional[dict[str, Any]] = None


class HeartbeatResponse(BaseModel):
    """Response to a heartbeat."""
    success: bool
    message: str


# ============================================
# Intent Routing Messages
# ============================================

class IntentParseRequest(BaseModel):
    """Request for LLM to parse user intent and route to service."""
    user_message: str
    user_id: Optional[str] = None
    context: Optional[dict[str, Any]] = None
    force_service: Optional[str] = Field(
        default=None,
        description="If set, skip intent parsing and use this service"
    )


class IntentParseResponse(BaseModel):
    """Response from intent parsing."""
    service_id: str
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    endpoint: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    reasoning: Optional[str] = None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)


# ============================================
# LLM Proxy Messages
# ============================================

class LLMProxyRequest(BaseModel):
    """Request to proxy LLM call through Gateway."""
    service_id: str  # Calling service ID for authentication
    messages: list[dict[str, str]]
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 800
    user_id: Optional[str] = None
    enable_web_search: bool = False


class LLMProxyResponse(BaseModel):
    """Response from LLM proxy."""
    content: str
    model: Optional[str] = None
    usage: Optional[dict[str, int]] = None


# ============================================
# Forced Mode Messages
# ============================================

class ForcedModeRequest(BaseModel):
    """Request to set/clear forced mode for a user."""
    user_id: str
    service_id: Optional[str] = Field(
        default=None,
        description="Service ID to force, or None to clear forced mode"
    )


class ForcedModeResponse(BaseModel):
    """Response to forced mode request."""
    success: bool
    message: str
    previous_service: Optional[str] = None
    current_service: Optional[str] = None


# ============================================
# Service Discovery Messages
# ============================================

class ServiceListResponse(BaseModel):
    """Response listing all registered services."""
    services: list[CapabilityInfo]
    total: int


class CapabilityListResponse(BaseModel):
    """Response listing all available capabilities."""
    capabilities: list[dict[str, Any]]
    total: int


# ============================================
# Helper Functions
# ============================================

def get_invest_capability() -> CapabilityInfo:
    """Get capability info for Invest service."""
    return CapabilityInfo(
        service_id="invest",
        service_name="投资分析服务",
        description="提供股票分析、回测、报告等投资相关功能，包括技术分析、基本面分析和投资建议",
        version="1.0.0",
        base_url="http://localhost:8010",
        endpoints=[
            EndpointInfo(
                path="/handle",
                method="POST",
                description="处理投资相关的消息，提供股票分析和投资建议",
                tags=["股票分析", "投资", "技术分析", "基本面分析", "回测"],
                parameters=[
                    ParamInfo(name="user_id", type="string", required=True, description="用户ID"),
                    ParamInfo(name="raw_text", type="string", required=True, description="用户消息内容"),
                ]
            ),
            EndpointInfo(
                path="/analyze",
                method="POST",
                description="分析指定股票的技术指标和基本面",
                tags=["股票分析", "技术分析"],
                parameters=[
                    ParamInfo(name="symbol", type="string", required=True, description="股票代码", example="600519"),
                    ParamInfo(name="days", type="integer", required=False, description="分析天数", default=365),
                ]
            ),
            EndpointInfo(
                path="/backtest",
                method="POST",
                description="对指定股票和策略进行回测",
                tags=["回测", "策略测试"],
                parameters=[
                    ParamInfo(name="symbol", type="string", required=True, description="股票代码"),
                    ParamInfo(name="strategy", type="string", required=False, description="策略名称", default="ma"),
                    ParamInfo(name="days", type="integer", required=False, description="回测天数", default=365),
                ]
            ),
        ],
        keywords=["股票", "分析", "投资", "回测", "报告", "技术指标", "均线", "K线", "基本面", "财务"],
        priority=10,
    )


def get_chat_capability() -> CapabilityInfo:
    """Get capability info for Chat service."""
    return CapabilityInfo(
        service_id="chat",
        service_name="通用对话服务",
        description="提供日常聊天、知识问答、网络搜索等功能，支持个性化对话",
        version="1.0.0",
        base_url="http://localhost:8011",
        endpoints=[
            EndpointInfo(
                path="/handle",
                method="POST",
                description="处理通用对话消息，支持个性化回复",
                tags=["聊天", "对话", "问答", "搜索"],
                parameters=[
                    ParamInfo(name="user_id", type="string", required=True, description="用户ID"),
                    ParamInfo(name="raw_text", type="string", required=True, description="用户消息内容"),
                ]
            ),
            EndpointInfo(
                path="/learning",
                method="POST",
                description="处理用户偏好学习",
                tags=["学习", "偏好"],
                parameters=[
                    ParamInfo(name="user_id", type="string", required=True, description="用户ID"),
                    ParamInfo(name="message", type="string", required=True, description="用户回复内容"),
                ]
            ),
        ],
        keywords=["聊天", "对话", "问答", "天气", "新闻", "搜索", "查询", "帮助", "什么", "怎么", "为什么"],
        priority=5,
    )


def get_dev_capability() -> CapabilityInfo:
    """Get capability info for Dev service."""
    return CapabilityInfo(
        service_id="dev",
        service_name="开发模式服务",
        description="提供代码开发、调试、问题解答等开发辅助功能，通过Claude Code CLI实现",
        version="1.0.0",
        base_url="http://localhost:8012",
        endpoints=[
            EndpointInfo(
                path="/handle",
                method="POST",
                description="处理开发相关的消息，通过Claude Code协助开发",
                tags=["开发", "代码", "调试", "编程"],
                parameters=[
                    ParamInfo(name="user_id", type="string", required=True, description="用户ID"),
                    ParamInfo(name="raw_text", type="string", required=True, description="用户消息内容"),
                ]
            ),
            EndpointInfo(
                path="/execute",
                method="POST",
                description="直接执行Claude Code命令",
                tags=["执行", "命令"],
                parameters=[
                    ParamInfo(name="prompt", type="string", required=True, description="执行提示"),
                    ParamInfo(name="working_dir", type="string", required=False, description="工作目录"),
                    ParamInfo(name="timeout", type="integer", required=False, description="超时秒数", default=120),
                ]
            ),
        ],
        keywords=["代码", "开发", "调试", "bug", "功能", "实现", "重构", "测试", "写代码", "编程"],
        priority=8,
    )


def get_llm_capability() -> CapabilityInfo:
    """Get capability info for LLM service."""
    return CapabilityInfo(
        service_id="llm",
        service_name="LLM服务",
        description="提供大语言模型对话、意图解析、网络搜索等核心LLM能力",
        version="1.0.0",
        base_url="http://localhost:8001",
        endpoints=[
            EndpointInfo(
                path="/handle",
                method="POST",
                description="处理用户消息，支持联网搜索",
                tags=["对话", "搜索", "问答"],
                parameters=[
                    ParamInfo(name="raw_text", type="string", required=True, description="用户消息"),
                    ParamInfo(name="user_id", type="string", required=False, description="用户ID"),
                ]
            ),
            EndpointInfo(
                path="/chat",
                method="POST",
                description="执行LLM对话，支持网络搜索",
                tags=["LLM", "对话", "生成"],
                parameters=[
                    ParamInfo(name="messages", type="array", required=True, description="消息列表"),
                    ParamInfo(name="system_prompt", type="string", required=False, description="系统提示"),
                    ParamInfo(name="enable_web_search", type="boolean", required=False, description="启用网络搜索", default=False),
                ]
            ),
            EndpointInfo(
                path="/intent",
                method="POST",
                description="解析消息意图",
                tags=["LLM", "意图", "解析"],
                parameters=[
                    ParamInfo(name="message", type="string", required=True, description="待解析消息"),
                ]
            ),
            EndpointInfo(
                path="/search",
                method="POST",
                description="执行网络搜索",
                tags=["搜索", "网络"],
                parameters=[
                    ParamInfo(name="query", type="string", required=True, description="搜索关键词"),
                    ParamInfo(name="max_results", type="integer", required=False, description="最大结果数", default=5),
                ]
            ),
        ],
        keywords=["LLM", "AI", "模型", "生成", "理解", "搜索", "联网"],
        priority=10,  # Higher priority for search-related queries
    )