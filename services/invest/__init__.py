"""Invest Service - Investment analysis capability.

This service handles investment-focused messages including
stock analysis, backtesting, and investment recommendations.
"""

from .main import create_app, run_invest_service

__all__ = ["create_app", "run_invest_service"]