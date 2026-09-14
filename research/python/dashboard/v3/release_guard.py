from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from research.python.robustness.common import read_json, sha256_file
from .contracts import DatasetFile, VisualizationReleaseV3
from .settings import VISUALIZATION_DATA_DIR,VISUALIZATION_MANIFEST_PATH,VISUALIZATION_RELEASE_ID,VISUALIZATION_VALIDATION_PATH,VISUALIZATION_VERSION

@dataclass(frozen=True)
class ReleaseGuardV3:
 ready:bool; release:VisualizationReleaseV3|None; errors:tuple[str,...]

@lru_cache(maxsize=1)
def get_v3_release_guard()->ReleaseGuardV3:
 errors=[]
 if not VISUALIZATION_MANIFEST_PATH.is_file(): return ReleaseGuardV3(False,None,(f"Missing {VISUALIZATION_MANIFEST_PATH}",))
 try:
  m=read_json(VISUALIZATION_MANIFEST_PATH); v=read_json(VISUALIZATION_VALIDATION_PATH)
  if m.get('gate')!='MULTIDATASET_VISUALIZATION_DATA_V3_READY': errors.append('M29 visualization gate is not ready.')
  if v.get('passed') is not True: errors.append('M29 visualization validation did not pass.')
  if m.get('release_id')!=VISUALIZATION_RELEASE_ID: errors.append('Unexpected visualization release id.')
  meta=read_json(VISUALIZATION_DATA_DIR/'release_metadata.json')
  if meta.get('visualization_version')!=VISUALIZATION_VERSION: errors.append('Unexpected visualization schema version.')
  files=[]
  for name,rec in sorted(m.get('files',{}).items()):
   p=VISUALIZATION_DATA_DIR/name
   if not p.is_file() or sha256_file(p)!=rec.get('sha256') or p.stat().st_size!=int(rec.get('byte_count',-1)): errors.append(f'Visualization artifact drift: {name}')
   else: files.append(DatasetFile(name,p,str(rec['sha256']),int(rec['byte_count'])))
  if errors: return ReleaseGuardV3(False,None,tuple(errors))
  release=VisualizationReleaseV3(str(meta['release_id']),str(meta['visualization_version']),str(meta['parent_release_id']),str(meta.get('replication_scope')),str(meta.get('robust_recommendation_status')),int(m['table_count']),tuple(files))
  return ReleaseGuardV3(True,release,())
 except Exception as e: return ReleaseGuardV3(False,None,(str(e),))
