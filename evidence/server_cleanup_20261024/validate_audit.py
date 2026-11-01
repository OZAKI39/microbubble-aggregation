"""Validate local audit artifacts and unchanged baseline, without deleting anything."""
from pathlib import Path
import gzip, hashlib, json, re, subprocess, datetime

E=Path(__file__).resolve().parent
ROOT=E.parents[1]
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
P=json.loads((E/'CANDIDATES.json').read_text())
B=json.loads((E/'LOCAL_BASELINE.json').read_text())
D=json.load(gzip.open(E/'REMOTE_DETAIL.json.gz','rt'))
I=json.load(gzip.open(E/'REMOTE_INVENTORY.json.gz','rt'))
rows=json.load(gzip.open(E/'CANDIDATE_ENTRY_IDENTITIES.json.gz','rt'))
targets=[t for g in P['groups'] for t in g['targets']]
paths=sorted(t['path'] for t in targets)
bad_overlaps=[(a,b) for a,b in zip(paths,paths[1:]) if b==a or b.startswith(a+'/')]
outside=[p for p in paths if not p.startswith(P['root']+'/')]
protected=json.loads((E/'PROTECTED_REMOTE_INDEX_CHECK.json').read_text())
protected_hits=[f['path'] for f in protected if any(f['path']==p or f['path'].startswith(p+'/') for p in paths)]
covered=set()
for s in D['snapshots']:
    for d in s['subdirs']:
        covered.update(f['path'] for f in d['files'] if f['match'])
for c in D['caches']:
    if c['eligible']:covered.update(f['path'] for f in c['files'])
unproven=[r['path'] for r in rows if r['group']=='A3' and r['kind']=='file' and P['root']+'/'+r['path'] not in covered]
archive_candidates=[s['archive']['path'] for s in D['snapshots'] if any(s['archive']['path']==p or s['archive']['path'].startswith(p+'/') for p in paths)]
changed=[]
for key in ['tracked_sha256','code_sha256']:
    for name,h in B[key].items():
        f=ROOT/name
        if not f.is_file() or sha(f)!=h:changed.append(dict(scope=key,path=name))
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
report=ROOT/'docs/SERVER_CLEANUP_AUDIT_20261024.md'
missing_links=[]
for target in re.findall(r'\]\(([^)]+)\)',report.read_text()):
    if '://' in target or target.startswith('#'):continue
    # These two files are created by this validation and its final checksums step.
    if target.endswith(('AUDIT_VALIDATION.json','SHA256SUMS.txt')):continue
    if not (report.parent/target).resolve().exists():missing_links.append(target)
single_link_regular_files=all(r['nlink']==1 for r in I['rows'] if r['kind']=='file')
passed=not any([bad_overlaps,outside,protected_hits,unproven,archive_candidates,changed,missing_links]) and head==B['head'] and all(f['hash_match'] and f['size_match'] for f in protected) and single_link_regular_files
out=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='PASS' if passed else 'FAIL',
    remote_deletion_executed=False,git_commit_or_push_executed=False,
    groups=len(P['groups']),exact_targets=len(paths),candidate_entries=len(rows),
    target_overlaps=bad_overlaps,targets_outside_project=outside,protected_file_hits=protected_hits,
    protected_remote_hashes_matching=sum(f['hash_match'] and f['size_match'] for f in protected),
    archive_files_in_candidates=archive_candidates,a3_unproven_files=unproven,
    unchanged_baseline_files=len(B['tracked_sha256']),unchanged_execution_code_files=len(B['code_sha256']),
    changed_baseline=changed,head_before=B['head'],head_after=head,
    missing_report_links=missing_links,all_regular_files_have_single_hardlink=single_link_regular_files,
    source_archive_coverage_note='A3 files match preserved tar members or belong to verified regenerable caches.',
    scope_note='Read-only audit only; live state and file contents must be checked again after explicit approval.')
(E/'AUDIT_VALIDATION.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
files=sorted(f for f in E.iterdir() if f.is_file() and f.name!='SHA256SUMS.txt')+[report]
(E/'SHA256SUMS.txt').write_text(''.join(f'{sha(f)}  {f.relative_to(ROOT)}\n' for f in files))
print(json.dumps(out,indent=2,ensure_ascii=False))
raise SystemExit(0 if passed else 1)
