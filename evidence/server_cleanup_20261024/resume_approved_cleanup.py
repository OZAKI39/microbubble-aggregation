"""Resume only still-present B3/B4 after a read-only directory scanner interrupted."""
from pathlib import Path
import base64,gzip,hashlib,json,subprocess,collections
E=Path(__file__).resolve().parent;X=E/'execution_A1_A2_B1_B4'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
A=json.loads((X/'AUTHORIZATION.json').read_text());plan=json.loads((E/'CANDIDATES.json').read_text())
assert sha(E/'CANDIDATES.json')==A['manifest_sha256']
assert sha(E/'CANDIDATE_ENTRY_IDENTITIES.json.gz')==A['identities_sha256']
journal=[json.loads(l) for l in (X/'DELETE_JOURNAL.jsonl').read_text().splitlines()]
deleted={x['path'] for x in journal if x['event']=='deleted'}
finished=[g for g in plan['groups'] if g['id'] in ['A1','A2','B1','B2']]
assert deleted=={t['path'] for g in finished for t in g['targets']}
assert journal[-1]['event']=='interrupted_active_dependency'
observed=json.loads((X/'INTERRUPT_PROCESS_CHECK.json').read_text())
assert observed['exe']=='/usr/local/lib/python3.12/dist-packages/tensorboard_data_server/bin/server'
assert not observed['project_fds'] and not observed['mapped_project_paths']
groups=[g for g in plan['groups'] if g['id'] in ['B3','B4']]
assert {g['id'] for g in groups}<set(A['approved_groups'])
entries=collections.defaultdict(list)
for row in json.load(gzip.open(E/'CANDIDATE_ENTRY_IDENTITIES.json.gz','rt')):
    if row['group'] in ['B3','B4']:entries[row['candidate_target']].append(row)
before=json.load(gzip.open(X/'PRE_INVENTORY.json.gz','rt'))
payload=dict(approved_groups=A['approved_groups'],manifest_sha256=A['manifest_sha256'],root=plan['root'],hostname=before['hostname'],groups=groups,entries=entries,git_roots=before['git_roots'],protected=json.loads((E/'PROTECTED_REMOTE_INDEX_CHECK.json').read_text()))
source="import json,gzip,base64\nP=json.loads(gzip.decompress(base64.b64decode("+repr(base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode())+")))\n"+(E/'remote_execute_approved.py').read_text()
log=X/'DELETE_RESUME_JOURNAL.jsonl';assert not log.exists()
(X/'RESUME_INPUT.json').write_text(json.dumps(dict(reason='TensorBoard briefly held a read-only directory FD in protected results; no process change/stop. Exclude only read-only directory scans outside approved targets from dependency blockers.',remaining_groups=['B3','B4'],authorization_manifest_sha256=A['manifest_sha256'],remote_script_sha256=sha(E/'remote_execute_approved.py')),indent=2)+'\n')
with (X/'DELETE_RESUME.ssh.stderr.log').open('wb') as err,log.open('w') as out:
    p=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','mevo-new','python3 -'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err)
    p.stdin.write(source.encode());p.stdin.close()
    for line in p.stdout:
        out.write(line.decode());out.flush()
        try:r=json.loads(line)
        except json.JSONDecodeError:continue
        if r['event'] not in ['deleted','skip','protected_hashes_before']:print(json.dumps(r),flush=True)
    code=p.wait();print('SSH exit:',code,flush=True);raise SystemExit(code)
