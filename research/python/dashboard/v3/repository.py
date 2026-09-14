from __future__ import annotations
from functools import lru_cache
import pandas as pd
from .contracts import CrossDatasetOverviewV3,StudyOverviewV3,VisualizationReleaseV3
from .release_guard import get_v3_release_guard
from .settings import DATASET_SCOPES,VISUALIZATION_DATA_DIR

class DashboardRepositoryV3:
 def __init__(self,release:VisualizationReleaseV3): self.release=release; self._cache={}
 def table(self,name:str)->pd.DataFrame:
  if name not in self._cache:
   p=VISUALIZATION_DATA_DIR/f'{name}.csv'
   if not p.is_file(): raise FileNotFoundError(p)
   self._cache[name]=pd.read_csv(p,low_memory=False)
  return self._cache[name].copy()

 def study_table(self,name:str,scope:str)->pd.DataFrame:
  self.validate_scope(scope)
  if scope=='CROSS_DATASET': raise ValueError('Cross-dataset is not a study table scope.')
  frame=self.table(name)
  if 'dataset_scope' not in frame.columns: raise ValueError(f'{name} has no dataset_scope column')
  return frame.loc[frame['dataset_scope'].astype(str).eq(scope)].reset_index(drop=True)
 def findings_for(self,scope:str)->pd.DataFrame:
  self.validate_scope(scope)
  frame=self.table('findings')
  return frame.loc[frame['dataset_scope'].astype(str).isin([scope,'GLOBAL'])].reset_index(drop=True)
 def limitations_for(self,scope:str)->pd.DataFrame:
  self.validate_scope(scope)
  frame=self.table('limitations')
  return frame.loc[frame['scope'].astype(str).isin([scope,'GLOBAL'])].reset_index(drop=True)
 def validate_scope(self,scope:str)->str:
  if scope not in DATASET_SCOPES: raise ValueError(f'Unsupported dataset scope: {scope}')
  return scope
 def study_overview(self,scope:str)->StudyOverviewV3:
  self.validate_scope(scope)
  if scope=='CROSS_DATASET': raise ValueError('Cross-dataset is a comparison scope, not a study scope.')
  s=self.table('study_summary').loc[lambda x:x.dataset_scope.astype(str).eq(scope)]
  if len(s)!=1: raise ValueError(f'Expected one study summary for {scope}')
  effects=self.table('omnibus_effects').loc[lambda x:x.dataset_scope.astype(str).eq(scope)]
  findings=self.table('findings').loc[lambda x:x.dataset_scope.astype(str).isin([scope,'GLOBAL'])]
  limitations=self.table('limitations').loc[lambda x:x.scope.astype(str).isin([scope,'GLOBAL'])]
  return StudyOverviewV3(scope,s.iloc[0].to_dict(),effects.reset_index(drop=True),findings.reset_index(drop=True),limitations.reset_index(drop=True))
 def cross_overview(self)->CrossDatasetOverviewV3:
  s=self.table('study_summary').set_index('dataset_scope')
  effects=self.table('cross_dataset_effects')
  findings=self.table('findings').loc[lambda x:x.dataset_scope.astype(str).isin(['CROSS_DATASET','GLOBAL'])]
  limitations=self.table('limitations').loc[lambda x:x.scope.astype(str).isin(['CROSS_DATASET','GLOBAL'])]
  return CrossDatasetOverviewV3(s.loc['HOME_CREDIT'].to_dict(),s.loc['FREDDIE'].to_dict(),self.release.replication_scope,self.release.robust_recommendation_status,effects.reset_index(drop=True),findings.reset_index(drop=True),limitations.reset_index(drop=True))

@lru_cache(maxsize=1)
def get_v3_repository()->DashboardRepositoryV3:
 guard=get_v3_release_guard()
 if not guard.ready or guard.release is None: raise RuntimeError('; '.join(guard.errors))
 return DashboardRepositoryV3(guard.release)
