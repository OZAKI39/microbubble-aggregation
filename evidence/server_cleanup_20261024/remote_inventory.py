"""Read-only server inventory. No file contents, credentials, or commands are changed."""
import os
import json
import stat
import time
import subprocess
import re
from pathlib import Path
from collections import defaultdict

ROOT = Path('/workspace/mevo_acoustic_microbubbles')
rows, links, instructions, errors = [], [], [], []
totals = defaultdict(lambda: dict(files=0, apparent_bytes=0, allocated_bytes=0, directories=0))
skip_detail = {'.venv', '.venv-render', '.python', '.postvenv', '.git'}
for base, dirs, files in os.walk(ROOT, followlinks=False):
    bp = Path(base)
    for name in dirs + files:
        p = bp/name
        try:
            st = p.lstat()
        except OSError as e:
            errors.append(dict(path=str(p), error=str(e)))
            continue
        rel = p.relative_to(ROOT)
        entry = dict(path=str(rel), bytes=st.st_size, allocated_bytes=st.st_blocks*512,
                     mtime_ns=st.st_mtime_ns, inode=st.st_ino, dev=st.st_dev,
                     nlink=st.st_nlink, mode=st.st_mode)
        if stat.S_ISLNK(st.st_mode):
            entry.update(kind='link', target=os.readlink(p), resolved=str(p.resolve()), exists=p.exists())
            links.append(entry)
        elif stat.S_ISDIR(st.st_mode):
            entry['kind']='directory'
        elif stat.S_ISREG(st.st_mode):
            entry['kind']='file'
        else:
            entry['kind']='special'
        # All sizes are per-path; hard links are explicitly recorded for later accounting.
        keys = [str(Path(*rel.parts[:i])) for i in range(1,min(4,len(rel.parts))+1)]
        for key in keys:
            t=totals[key]
            if entry['kind']=='file': t['files']+=1; t['apparent_bytes']+=st.st_size
            elif entry['kind']=='directory': t['directories']+=1
            t['allocated_bytes']+=st.st_blocks*512
        if name=='AGENTS.md' and not any(k in skip_detail for k in rel.parts):
            if p.is_file(): instructions.append(dict(path=str(p), text=p.read_text(errors='replace')))
        # Keep all metadata, including environments, to support exact pre-delete rechecks.
        rows.append(entry)

def command(args, cwd=None):
    p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,
                     env={**os.environ,'GIT_OPTIONAL_LOCKS':'0'},timeout=45)
    return dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)

git_roots=[]
for entry in rows:
    if Path(entry['path']).name=='.git':
        p=ROOT/entry['path']; root=p.parent
        git_roots.append(dict(path=str(root),head=command(['git','rev-parse','HEAD'],root),
                             status=command(['git','status','--porcelain=v1','-uall'],root),
                             worktrees=command(['git','worktree','list','--porcelain'],root),
                             refs=command(['git','for-each-ref','--format=%(refname) %(objectname)'],root)))

process_refs=[]
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit(): continue
    try:
        hits=[]
        for item in [proc/'cwd',proc/'exe',*list((proc/'fd').iterdir())]:
            try:
                target=os.readlink(item)
                if target.startswith(str(ROOT)): hits.append(dict(kind=item.name,path=target))
            except OSError: pass
        cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        # Never export full commands; they can contain unrelated platform credentials.
        if str(ROOT) in cmd: hits.append(dict(kind='command_path_reference',path=str(ROOT)))
        if hits: process_refs.append(dict(pid=int(proc.name),comm=(proc/'comm').read_text().strip(),references=hits))
    except OSError: pass

supervisor=[]
for p in Path('/etc/supervisor/conf.d').glob('*'):
    if p.is_file():
        txt=p.read_text(errors='replace')
        if str(ROOT) in txt:
            supervisor.append(dict(path=str(p),
                                   referenced_paths=sorted(set(re.findall(r'/workspace/mevo_acoustic_microbubbles/[^\s\"\x27,;]+',txt))),
                                   settings=[line for line in txt.splitlines() if line.startswith(('autostart=','autorestart=','[program:'))]))

activation={}
for name in ['activate.sh','activate-render.sh']:
    p=ROOT/name
    if p.is_file():activation[name]=p.read_text()

print(json.dumps(dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),root=str(ROOT),
                     hostname=os.uname().nodename,rows=rows,totals=dict(totals),links=links,
                     instructions=instructions,errors=errors,git_roots=git_roots,
                     process_refs=process_refs,supervisor=supervisor,activation=activation,
                     supervisor_status=command(['supervisorctl','status']),
                     disk=command(['df','-B1',str(ROOT)])),ensure_ascii=False))
