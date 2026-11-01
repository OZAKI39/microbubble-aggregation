"""Execute only the user's approved, immutable manifest; P is supplied over stdin.

No wildcard deletion, symlink traversal, Git mutation, service action, or data cleanup.
"""
import os, stat, json, time, hashlib, shutil, subprocess
from pathlib import Path

R=Path('/workspace/mevo_acoustic_microbubbles')
approved=['A1','A2','B1','B2','B3','B4']
assert P['approved_groups']==approved
assert P['root']==str(R) and R.resolve()==R
assert shutil.rmtree.avoids_symlink_attacks
started=time.monotonic()
def emit(event,**data):print(json.dumps(dict(event=event,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**data)),flush=True)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def command(args,cwd=None):
    p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=45,env={**os.environ,'GIT_OPTIONAL_LOCKS':'0'})
    return dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
def git_state(root):
    return dict(path=root,head=command(['git','rev-parse','HEAD'],root),
                status=command(['git','status','--porcelain=v1','-uall'],root),
                worktrees=command(['git','worktree','list','--porcelain'],root),
                refs=command(['git','for-each-ref','--format=%(refname) %(objectname)'],root))
def busy():
    found=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
        try:
            hits=[]
            for item in [proc/'cwd',proc/'exe',*list((proc/'fd').iterdir())]:
                try:
                    s=os.readlink(item)
                    if s.startswith(str(R)+'/') or s==str(R):
                        # A read-only directory scan outside all approved targets is
                        # not a dependency on a retired environment (e.g. TensorBoard).
                        is_fd=item.parent.name=='fd'
                        touches_target=any(s==t['path'] or s.startswith(t['path']+'/') for g in P['groups'] for t in g['targets'])
                        read_only_directory=False
                        if is_fd and not touches_target:
                            try:
                                fd_flags=int(next(l.split()[1] for l in (proc/'fdinfo'/item.name).read_text().splitlines() if l.startswith('flags:')),8)
                                read_only_directory=stat.S_ISDIR(item.stat().st_mode) and (fd_flags & os.O_ACCMODE)==os.O_RDONLY
                            except (OSError,StopIteration,ValueError):pass
                        if not read_only_directory:hits.append(dict(kind=item.name,path=s))
                except OSError:pass
            cmd=(proc/'cmdline').read_bytes()
            if str(R).encode() in cmd:hits.append(dict(kind='command_reference',path=str(R)))
            maps=proc/'maps'
            if maps.exists() and str(R) in maps.read_text(errors='replace'):hits.append(dict(kind='memory_map',path=str(R)))
            # Inspect only dependency variables; never export full process environments.
            try:
                env=(proc/'environ').read_bytes().split(b'\0')
                if any(e.startswith((b'VIRTUAL_ENV=',b'PYTHONPATH=')) and str(R).encode() in e for e in env):hits.append(dict(kind='environment_dependency',path=str(R)))
            except OSError:pass
            if hits:found.append(dict(pid=int(proc.name),comm=(proc/'comm').read_text().strip(),references=hits))
        except (OSError,ProcessLookupError):pass
    return found
def metadata(p):
    s=p.lstat()
    row=dict(path=str(p.relative_to(R)),bytes=s.st_size,allocated_bytes=s.st_blocks*512,
             mtime_ns=s.st_mtime_ns,inode=s.st_ino,dev=s.st_dev,nlink=s.st_nlink,mode=s.st_mode)
    if stat.S_ISLNK(s.st_mode):row.update(kind='link',target=os.readlink(p))
    elif stat.S_ISDIR(s.st_mode):row['kind']='directory'
    elif stat.S_ISREG(s.st_mode):row['kind']='file'
    else:row['kind']='special'
    return row
def tree(p):
    rows=[metadata(p)]
    if rows[0]['kind']=='directory':
        for base,dirs,files in os.walk(p,followlinks=False):
            for n in dirs+files:rows.append(metadata(Path(base)/n))
    return {r['path']:r for r in rows}
fields=['bytes','mtime_ns','inode','dev','nlink','mode','kind','target']
def inspect(t):
    p=Path(t['path'])
    if p.parent.resolve()!=p.parent:return ['symlink_or_changed_ancestor']
    try:actual=tree(p)
    except OSError as e:return [type(e).__name__+': '+str(e)]
    expected={r['path']:r for r in P['entries'][t['path']]}
    errors=[]
    if actual.keys()!=expected.keys():errors.append('entry_set_changed')
    for name in actual.keys()&expected.keys():
        if any(actual[name].get(k)!=expected[name].get(k) for k in fields):errors.append('metadata_changed:'+name)
    return errors

env_paths={'B1':R/'f10ab_shape_20261018/.postvenv','B2':R/'f10ac_ad_20261018/.venv',
           'B3':R/'f10ae_target_20261019/.venv','B4':R/'f10af_observable_20261019/.venv'}
targets=[t for g in P['groups'] for t in g['targets']]
all_paths=sorted(t['path'] for t in targets)
assert len(all_paths)==len(set(all_paths))
for a,b in zip(all_paths,all_paths[1:]):assert not b.startswith(a+'/')
for g in P['groups']:
    assert g['id'] in approved
    for t in g['targets']:
        p=Path(t['path']);parts=p.relative_to(R).parts
        assert len(parts)>1 and '.git' not in parts
        if g['id']=='A1':assert p==R/'f10ae_target_20261019/.venv_incomplete_download'
        elif g['id']=='A2':
            assert p.name in ['__pycache__','.pytest_cache','.ruff_cache'] and parts[0].startswith('f') and parts[0]!='f7'
            assert not any(x.startswith('.venv') or x in ['.postvenv','.python'] for x in parts)
        elif t['type']=='directory':assert p==env_paths[g['id']]
        else:
            assert t['type']=='symlink_only'
            assert p.resolve()==env_paths[g['id']]

emit('begin',approved_groups=approved,excluded_group='A3',target_count=len(targets),manifest_sha256=P['manifest_sha256'])
assert os.uname().nodename==P['hostname']
active=busy()
emit('process_check',references=active)
if active:raise RuntimeError('Project process dependency exists; nothing deleted')
for before in P['git_roots']:assert git_state(before['path'])==before,'Git state changed'
initial_errors={t['path']:inspect(t) for t in targets}
skip={p:errors for p,errors in initial_errors.items() if errors}
# Retire each environment and its shortcuts together, or skip the whole group.
for g in P['groups']:
    if g['id'].startswith('B') and any(t['path'] in skip for t in g['targets']):
        for t in g['targets']:skip.setdefault(t['path'],['environment_group_changed'])
emit('precheck',eligible=len(targets)-len(skip),skipped=skip)
protected=[]
for f in P['protected']:
    p=Path(f['path'])
    ok=p.is_file() and p.stat().st_size==f['bytes'] and sha(p)==f['sha256']
    protected.append(dict(path=str(p),match=ok))
emit('protected_hashes_before',files=protected)
assert all(f['match'] for f in protected),'Protected data changed; nothing deleted'
before_du=command(['du','-sx','-B1',str(R)])
before_df=command(['df','-B1',str(R)])
emit('disk_before',du=before_du,df=before_df)
deleted=[]
for g in P['groups']:
    active=busy()
    if active:emit('interrupted_active_dependency',references=active);raise RuntimeError('New process dependency; stopped')
    if g['id'].startswith('B'):
        changed={t['path']:inspect(t) for t in g['targets'] if t['path'] not in skip}
        if any(changed.values()):
            for t in g['targets']:skip.setdefault(t['path'],['environment_group_changed_before_delete'])
    for i,t in enumerate(g['targets']):
        path=t['path'];p=Path(path)
        if path in skip:emit('skip',group=g['id'],path=path,reasons=skip[path]);continue
        if i%100==0:
            active=busy()
            if active:emit('interrupted_active_dependency',references=active);raise RuntimeError('New process dependency; stopped')
        errors=inspect(t)
        if errors:
            skip[path]=errors;emit('skip',group=g['id'],path=path,reasons=errors);continue
        # rmtree is fd-based and never follows symlink entries. For shortcuts, unlink only.
        if t['type']=='symlink_only':p.unlink()
        else:shutil.rmtree(p)
        assert not os.path.lexists(p)
        row=dict(group=g['id'],path=path,allocated_bytes=t['allocated_bytes'],type=t['type'])
        deleted.append(row);emit('deleted',**row)
    emit('group_complete',group=g['id'],deleted=sum(x['group']==g['id'] for x in deleted),skipped=sum(t['path'] in skip for t in g['targets']))
for before in P['git_roots']:assert git_state(before['path'])==before,'Git changed after deletion'
emit('complete',deleted_targets=len(deleted),skipped_targets=len(skip),deleted_allocated_bytes=sum(x['allocated_bytes'] for x in deleted),
     elapsed_seconds=time.monotonic()-started,du=command(['du','-sx','-B1',str(R)]),df=command(['df','-B1',str(R)]))
