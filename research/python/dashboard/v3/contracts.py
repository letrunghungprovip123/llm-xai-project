from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import pandas as pd

@dataclass(frozen=True)
class DatasetFile:
 name:str; path:Path; sha256:str; byte_count:int

@dataclass(frozen=True)
class VisualizationReleaseV3:
 release_id:str; version:str; parent_release_id:str; replication_scope:str; robust_recommendation_status:str; table_count:int; files:tuple[DatasetFile,...]

@dataclass(frozen=True)
class StudyOverviewV3:
 dataset_scope:str; summary:dict[str,object]; effects:pd.DataFrame; findings:pd.DataFrame; limitations:pd.DataFrame

@dataclass(frozen=True)
class CrossDatasetOverviewV3:
 home_credit:dict[str,object]; freddie:dict[str,object]; replication_scope:str; robust_recommendation_status:str; effects:pd.DataFrame; findings:pd.DataFrame; limitations:pd.DataFrame
