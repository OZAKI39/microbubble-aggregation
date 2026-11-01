"""Capture fresh read-only server evidence; no server files are written."""
from pathlib import Path
import ast, concurrent.futures, datetime, gzip, hashlib, json, subprocess, sys

E=Path(__file__).resolve().parent
X=E/'execution_A1_A2_B1_B4'
X.mkdir(exist_ok=True)
phase=sys.argv[1]
assert phase in ['PRE','POST']
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
if phase=='PRE':
    auth=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              user_instruction='批准 A1–A2、B1–B4',approved_groups=['A1','A2','B1','B2','B3','B4'],
              explicitly_excluded_group='A3',manifest_sha256=sha(E/'CANDIDATES.json'),
              identities_sha256=sha(E/'CANDIDATE_ENTRY_IDENTITIES.json.gz'),
              source_audit='docs/SERVER_CLEANUP_AUDIT_20261024.md')
    p=X/'AUTHORIZATION.json'
    if p.exists():assert json.loads(p.read_text())['manifest_sha256']==auth['manifest_sha256']
    else:p.write_text(json.dumps(auth,ensure_ascii=False,indent=2)+'\n')
tree=ast.parse((E/'collect_reference_evidence.py').read_text())
refscript=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='script' for t in n.targets))
scripts={'INVENTORY':(E/'remote_inventory.py').read_text()}
if phase=='PRE':scripts.update(DETAIL=(E/'remote_detail.py').read_text(),REFERENCES=refscript)
def capture(item):
    name,source=item
    wrapper='import contextlib,io,gzip,sys\nb=io.StringIO()\nwith contextlib.redirect_stdout(b):\n exec('+repr(source)+',{})\nsys.stdout.buffer.write(gzip.compress(b.getvalue().encode()))\n'
    p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','mevo-new','python3 -'],input=wrapper.encode(),capture_output=True,timeout=240)
    (X/f'{phase}_{name}.ssh.stderr.log').write_bytes(p.stderr)
    if p.returncode:raise RuntimeError((name,p.returncode,p.stderr.decode(errors='replace')))
    value=json.loads(gzip.decompress(p.stdout))
    dest=X/f'{phase}_{name}.json.gz'
    assert not dest.exists(),f'Preserve existing evidence: {dest}'
    dest.write_bytes(p.stdout)
    return dict(name=name,bytes=len(p.stdout),path=str(dest),keys=list(value))
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for result in pool.map(capture,scripts.items()):print(json.dumps(result),flush=True)
