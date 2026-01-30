"""Docstring for blackbox-exporter-operator.src.models.

This models module will hold ops-independent classes to be used by charm code for data validation.
"""
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    """BaseModel for a config file."""
    modules: Dict[str, Any]

class StaticConfig(BaseModel):
    targets: List[str] = Field(..., min_items=1)  # must have at least one target

class ScrapeJob(BaseModel):
    job_name: str
    metrics_path: str
    params: Dict[str, List[str]]  # e.g., {"module": ["http_2xx"]}
    static_configs: List[StaticConfig] = Field(..., min_items=1)
    modules: List[str] = Field(..., min_items=1)

    @field_validator("job_name")
    @classmethod
    def job_name_not_empty(cls, v):
        if not v.strip():
            raise ValueError("job_name cannot be empty")
        return v

    @field_validator("metrics_path")
    @classmethod
    def metrics_path_must_be_probes(cls, v):
        if v != "/probe":
            raise ValueError('metrics_path must be "/probe"')
        return v


class ProbesFile(BaseModel):
    scrape_configs: List[ScrapeJob] = Field(..., min_items=1)
