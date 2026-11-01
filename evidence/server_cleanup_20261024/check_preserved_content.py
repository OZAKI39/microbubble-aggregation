"""Verify protected remote data and retained environment; no simulations."""
from pathlib import Path
import json,subprocess
E=Path(__file__).resolve().parent;X=E/'execution_A1_A2_B1_B4'
protected=json.loads((E/'PROTECTED_REMOTE_INDEX_CHECK.json').read_text())
script='protected='+repr(protected)+'\n'+r'''
from pathlib import Path
import json,hashlib,subprocess,time
out=[]
for f in protected:
    p=Path(f['path'])
    item=dict(path=str(p),exists=p.is_file())
    if item['exists']:
        with p.open('rb') as h:digest=hashlib.file_digest(h,'sha256').hexdigest()
        item.update(sha256=digest,bytes=p.stat().st_size,match=digest==f['sha256'] and p.stat().st_size==f['bytes'])
    else:item['match']=False
    out.append(item)
py='/workspace/mevo_acoustic_microbubbles/f10ag_capture_20261019/.venv/bin/python'
code="import sys,json,numpy,scipy,h5py,osqp; print(json.dumps({'prefix':sys.prefix,'numpy':numpy.__version__,'scipy':scipy.__version__,'h5py':h5py.__version__,'osqp':osqp.__version__}))"
p=subprocess.run([py,'-I','-B','-c',code],capture_output=True,text=True,timeout=45)
print(json.dumps(dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),protected_files=out,
                     retained_F10AG_import_check=dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr),
                     status='PASS' if all(f['match'] for f in out) and p.returncode==0 else 'FAIL')))
'''
p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','mevo-new','python3 -'],input=script,capture_output=True,text=True,timeout=120)
(X/'POST_CONTENT.ssh.stderr.log').write_text(p.stderr)
assert p.returncode==0,(p.returncode,p.stderr)
value=json.loads(p.stdout)
(X/'POST_CONTENT.json').write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps(dict(status=value['status'],protected_files=len(value['protected_files']),retained_F10AG_import_check=value['retained_F10AG_import_check'])))
assert value['status']=='PASS'
