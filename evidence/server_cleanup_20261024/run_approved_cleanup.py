"""Validate the immutable approval evidence and stream the exact scoped operation."""
from pathlib import Path
import base64, gzip, hashlib, json, subprocess, collections

E=Path(__file__).resolve().parent;X=E/'execution_A1_A2_B1_B4'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(n):return json.load(gzip.open(n,'rt'))
A=json.loads((X/'AUTHORIZATION.json').read_text())
assert A['user_instruction']=='批准 A1–A2、B1–B4'
assert A['manifest_sha256']==sha(E/'CANDIDATES.json')
assert A['identities_sha256']==sha(E/'CANDIDATE_ENTRY_IDENTITIES.json.gz')
plan=json.loads((E/'CANDIDATES.json').read_text());old=load(E/'REMOTE_INVENTORY.json.gz');new=load(X/'PRE_INVENTORY.json.gz')
assert old['git_roots']==new['git_roots']
assert not new['errors'] and not new['process_refs']
assert old['instructions']==new['instructions']
assert old['supervisor']==new['supervisor']
for filename,oldname,keys in [('DETAIL','REMOTE_DETAIL.json.gz',['outside_project_references']),('REFERENCES','REFERENCE_EVIDENCE.json.gz',['cross_stage_references','outside_links'])]:
    before=load(E/oldname);after=load(X/f'PRE_{filename}.json.gz')
    for key in keys:assert before[key]==after[key],f'Path references changed: {key}'
groups=[g for g in plan['groups'] if g['id'] in A['approved_groups']]
assert [g['id'] for g in groups]==A['approved_groups'] and all(g['id']!='A3' for g in groups)
targets={t['path']:t for g in groups for t in g['targets']}
entries=collections.defaultdict(list)
for row in load(E/'CANDIDATE_ENTRY_IDENTITIES.json.gz'):
    if row['group'] in A['approved_groups']:entries[row['candidate_target']].append(row)
fresh=collections.defaultdict(list)
R=Path(plan['root'])
for row in new['rows']:
    p=R/row['path']
    for q in [p,*p.parents]:
        if str(q) in targets:fresh[str(q)].append(row);break
        if q==R:break
changes=[]
for path,rows in entries.items():
    a={r['path']:r for r in rows};b={r['path']:r for r in fresh[path]}
    if a.keys()!=b.keys():changes.append(path);continue
    if any(any(a[p].get(k)!=b[p].get(k) for k in ['kind','bytes','mtime_ns','inode','dev','nlink','mode','target']) for p in a):changes.append(path)
assert not changes,changes
# All incoming links into approved trees must themselves be inside approved trees.
def selected(path):
    p=Path(path)
    return any(str(q) in targets for q in [p,*p.parents])
incoming=[r for r in new['links'] if selected(r['resolved']) and not selected(str(R/r['path']))]
assert not incoming,incoming
payload=dict(approved_groups=A['approved_groups'],manifest_sha256=A['manifest_sha256'],root=plan['root'],
             hostname=new['hostname'],groups=groups,entries=entries,git_roots=new['git_roots'],
             protected=json.loads((E/'PROTECTED_REMOTE_INDEX_CHECK.json').read_text()))
encoded=base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode()
source="import json,gzip,base64\nP=json.loads(gzip.decompress(base64.b64decode("+repr(encoded)+")))\n"+(E/'remote_execute_approved.py').read_text()
log=X/'DELETE_JOURNAL.jsonl';err=X/'DELETE.ssh.stderr.log'
assert not log.exists(),'Existing journal found: inspect before attempting any resume'
(X/'EXECUTION_INPUT.json').write_text(json.dumps(dict(manifest_sha256=A['manifest_sha256'],remote_script_sha256=sha(E/'remote_execute_approved.py'),approved_groups=A['approved_groups'],excluded_group='A3',targets=len(targets),expected_allocated_bytes=sum(t['allocated_bytes'] for t in targets.values()),precheck='PASS'),indent=2)+'\n')
with err.open('wb') as stderr,log.open('w') as out:
    p=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','mevo-new','python3 -'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr)
    p.stdin.write(source.encode());p.stdin.close()
    for line in p.stdout:
        out.write(line.decode());out.flush()
        try:row=json.loads(line)
        except json.JSONDecodeError:continue
        if row['event'] not in ['deleted','skip','protected_hashes_before']:
            print(json.dumps(row),flush=True)
    code=p.wait()
    print('SSH exit:',code,flush=True)
    raise SystemExit(code)
