"""Collect narrowly scoped remote path references, without exporting command secrets."""
import subprocess,json,gzip
from pathlib import Path

out=Path(__file__).resolve().parent
script=r'''
import os,json,re
from pathlib import Path
R=Path('/workspace/mevo_acoustic_microbubbles'); refs=[]; outside_links=[]
for base,dirs,files in os.walk(R,followlinks=False):
 b=Path(base);dirs[:]=[n for n in dirs if n not in ['.git','lib','lib64','results','__pycache__','.postvenv','.python'] and not n.startswith('.venv')]
 for n in files:
  p=b/n
  if p.suffix not in ['.py','.sh','.cfg','.conf','.pth'] or p.is_symlink() or p.stat().st_size>2000000:continue
  for i,line in enumerate(p.read_text(errors='replace').splitlines(),1):
   if str(R) not in line:continue
   targets=re.findall(r'/workspace/mevo_acoustic_microbubbles/[A-Za-z0-9_./+\-]+',line)
   for target in targets:
    t=Path(target)
    if len(t.parts)>3 and t.parts[3]!=p.relative_to(R).parts[0]:
     refs.append({'source':str(p),'line':i,'target':target,'target_exists':t.exists()})
for top in Path('/workspace').iterdir():
 if not top.is_dir() or top==R or top.name.startswith('.'):continue
 for base,dirs,files in os.walk(top,followlinks=False):
  b=Path(base)
  for n in dirs+files:
   p=b/n
   if p.is_symlink():
    t=str(p.resolve())
    if t.startswith(str(R)):outside_links.append({'path':str(p),'target':t})
  dirs[:]=[n for n in dirs if n not in ['.git','node_modules','site-packages','__pycache__','results','data','runtime','models'] and not n.startswith('.venv')]
print(json.dumps({'cross_stage_references':refs,'outside_links':outside_links}))
'''
p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','mevo-new','python3 -'],input=script,capture_output=True,text=True,timeout=120)
(out/'references_ssh.stderr.log').write_text(p.stderr)
if p.returncode:raise SystemExit(p.stderr)
a=json.loads(p.stdout)
with gzip.open(out/'REFERENCE_EVIDENCE.json.gz','wt') as f:json.dump(a,f)
print(json.dumps({'cross_stage_references':len(a['cross_stage_references']),'outside_links':a['outside_links']}))
