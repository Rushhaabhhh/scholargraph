#!/usr/bin/env python3
"""Explicit one-time Vosk model preparation. Runtime never downloads weights."""
import os,hashlib,json,shutil,tempfile,urllib.request,zipfile
from pathlib import Path
URL='https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip'
target=Path(os.environ.get('SCHOLARGRAPH_VOSK_MODEL',str(Path(__file__).resolve().parents[1]/'data/models/vosk-en')))
if target.exists():raise SystemExit(f'Model already exists: {target}')
target.parent.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(dir=target.parent,prefix='.voice-') as temporary:
 root=Path(temporary);archive=root/'model.zip'
 print('Downloading the 40 MB Apache-2.0 English Vosk model...',flush=True)
 urllib.request.urlretrieve(URL,archive)
 with zipfile.ZipFile(archive) as z:
  for name in z.namelist():
   if not (root/ name).resolve().is_relative_to(root.resolve()):raise ValueError('Unsafe archive path')
  z.extractall(root)
 extracted=root/'vosk-model-small-en-us-0.15';required=['am/final.mdl','conf/model.conf','graph/HCLr.fst','graph/Gr.fst']
 if not all((extracted/f).is_file() for f in required):raise ValueError('Incomplete model')
 (extracted/'scholargraph-provenance.json').write_text(json.dumps({'source':URL,'license':'Apache-2.0 per Vosk model catalogue','archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':{str(p.relative_to(extracted)):hashlib.sha256(p.read_bytes()).hexdigest() for p in extracted.rglob('*') if p.is_file()}},indent=2))
 shutil.move(extracted,target)
 print(f'Prepared offline model: {target}',flush=True)
