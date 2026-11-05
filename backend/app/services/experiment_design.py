"""Deterministic experiment design drafts from explicit user inputs."""
from itertools import product
from math import prod
from random import Random
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class Factor(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    levels: list[str] = Field(min_length=2, max_length=8)

    @field_validator("levels")
    @classmethod
    def distinctLevels(cls, values):
        cleaned = [value.strip() for value in values]
        if any(not value or len(value) > 60 for value in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("Levels must be distinct nonempty values")
        return cleaned


class DesignContext(BaseModel):
    origin: Literal["compare", "falsification", "gaps"]
    paperIds: list[str] = Field(default_factory=list, max_length=20)
    recordIds: list[str] = Field(default_factory=list, max_length=100)
    sourcePages: dict[str, Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=20)]] = Field(
        default_factory=dict, max_length=20,
    )
    conditions: dict[str, str] = Field(default_factory=dict, max_length=8)


class DesignRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    context: DesignContext | None = None
    factors: list[Factor] = Field(default_factory=list, max_length=4)
    outcome: str = Field(default="", max_length=100)
    control: dict[str, str] | None = None
    replicates: int | None = Field(default=None, ge=1, le=30)
    maxUnits: int | None = Field(default=None, ge=1, le=1000)
    seed: int = 17


class DesignGroup(BaseModel):
    id: str
    levels: dict[str, str]
    isControl: bool
    sourceType: Literal["userProvided", "proposed"] = "userProvided"


def planExperiment(req: DesignRequest, *, sourceType: Literal["userProvided", "proposed"] = "userProvided") -> dict:
    factors = req.factors
    names = [factor.name for factor in factors]
    if len(set(names)) != len(names):
        raise ValueError("Factor names must be distinct")
    if req.control is not None and (
        set(req.control) != set(names) or any(req.control[f.name] not in f.levels for f in factors)
    ):
        raise ValueError("Control must select one valid level of every factor")
    count = prod(len(factor.levels) for factor in factors) if factors else 0
    total = count * req.replicates if count and req.replicates else None
    pending = []
    for missing, label in (
        (not factors, "确认因素和水平"), (not req.outcome.strip(), "确认主要响应指标"),
        (req.control is None, "确认基准对照"), (req.replicates is None, "确认独立重复数"),
        (req.maxUnits is None, "确认可用实验单位"), (True, "核查设备、资源及伦理安全要求"),
    ):
        if missing:
            pending.append(label)
    exceeds = count > 128 or (req.maxUnits is not None and (total or count) > req.maxUnits)
    groups = []
    if factors and not exceeds:
        for index, values in enumerate(product(*(factor.levels for factor in factors)), 1):
            levels = dict(zip(names, values))
            groups.append(DesignGroup(id=f"G{index}", levels=levels, isControl=levels == req.control, sourceType=sourceType))
    order = [f"{group.id}-R{repeat}" for group in groups for repeat in range(1, (req.replicates or 0) + 1)]
    Random(req.seed).shuffle(order)
    return {
        "designType": "single_factor" if len(factors) == 1 else "full_factorial" if factors else "pending",
        "combinationCount": count, "totalExperimentalUnits": total, "groups": groups,
        "randomizationSeed": req.seed, "randomizationOrder": order, "exceedsLimit": exceeds,
        "hypotheses": {
            "null": f"在所选实验条件下，{req.outcome}在各组间无差异。" if factors and req.outcome.strip() else None,
            "alternative": f"在所选实验条件下，至少一组的{req.outcome}不同。" if factors and req.outcome.strip() else None,
        },
        "pending": pending,
        "statisticalPlan": "先定义独立实验单位与主要对比。报告效应量和区间。需先确认方差、目标效应与功效，再确定样本量。",
    }

