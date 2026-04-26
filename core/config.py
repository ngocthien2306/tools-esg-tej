from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class ModelSpec(BaseModel):
    name: str
    extra_vars: List[str] = Field(default_factory=list)
    filter_col: Optional[str] = None
    filter_op: Literal[">", ">=", "<", "<=", "=="] = ">"
    filter_value: float = 0.0
    label: str = ""


class AnalysisConfig(BaseModel):
    dataset_id: str
    target: str

    base_features: List[str] = Field(default_factory=list)
    revenue_vars: List[str] = Field(default_factory=list)

    winsorize_limits: List[float] = Field(default_factory=lambda: [0.01, 0.01])
    winsorize_cols: List[str] = Field(default_factory=list)
    log_transform_cols: List[str] = Field(default_factory=list)

    entity_col: str = "COID"
    time_col: str = "Year"
    industry_col: Optional[str] = "TEJ Industry ID"

    base_lag: int = 1
    rev_lag: int = 1

    entity_effects: bool = False
    time_effects: bool = True
    industry_effects: bool = True
    cluster_entity: bool = True

    year_min: Optional[int] = None
    year_max: Optional[int] = None

    did_enabled: bool = False
    did_treat_col: Optional[str] = None
    did_cutoff_method: Literal["median_pre", "value"] = "median_pre"
    did_cutoff_value: Optional[float] = None
    did_post_year: int = 2021

    models: List[ModelSpec] = Field(default_factory=list)
    note: str = ""
