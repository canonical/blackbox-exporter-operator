"""Docstring for blackbox-exporter-operator.src.models.

This models module will hold ops-independent classes to be used by charm code for data validation.
"""
from typing import Any, Dict

from pydantic import BaseModel


class Config(BaseModel):
    """BaseModel for a config file."""
    modules: Dict[str, Any]
