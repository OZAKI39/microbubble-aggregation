"""Read-only candidate proof: cache/source correspondence and archive identity."""
import os,json,stat,hashlib,tarfile,re,time
from pathlib import Path
from collections import defaultdict
import importlib.util

R=Path('/workspace/mevo_acoustic_microbubbles')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def meta(p):
    s=p.lstat()
    return dict(path=str(p),bytes=s.st_size,allocated_bytes=s.st_blocks*512,
                mtime_ns=s.st_mtime_ns,inode=s.st_ino,dev=s.st_dev,nlink=s.st_nlink)

caches=[]; snapshots=[]; environments=[]; references=[]
for base,dirs,files in os.walk(R,followlinks=False):
    b=Path(base)
    if b.name in ['__pycache__','.pytest_cache','.ruff_cache']:
        check=[]; eligible=True
        for d,sub,fs in os.walk(b,followlinks=False):
            for n in fs:
                p=Path(d)/n
                if p.is_symlink():eligible=False;check.append(dict(path=str(p),reason='symlink'));continue
                row=meta(p)
                if b.name=='__pycache__':
                    if p.suffix!='.pyc':eligible=False;row['reason']='not_pyc'
                    else:
                        try:source=Path(importlib.util.source_from_cache(str(p)))
                        except ValueError:source=Path('/__invalid__')
                        row['source']=str(source)
                        if not source.is_file():eligible=False;row['reason']='source_missing'
                check.append(row)
        if check:caches.append(dict(path=str(b),eligible=eligible,files=check))
        dirs[:]=[]
    if b.name in ['.git']:
        dirs[:]=[]
    if 'source.tar.gz' in files and ('.execution' in b.parts or 'execution' in b.parts):
        archive=b/'source.tar.gz'; row=dict(directory=str(b),archive=meta(archive),archive_sha256=sha(archive),subdirs=[],problems=[])
        try:
            with tarfile.open(archive,'r:gz') as tf:
                members={m.name.lstrip('./'):m for m in tf.getmembers() if m.isfile()}
                for d in sorted(b.iterdir()):
                    if not d.is_dir() or d.is_symlink() or d.name.startswith('.') or d.name=='results':continue
                    fs=[];ok=True
                    for bb,dd,ff in os.walk(d,followlinks=False):
                        if any((Path(bb)/n).is_symlink() for n in dd):ok=False
                        for n in ff:
                            p=Path(bb)/n; rel=str(p.relative_to(b))
                            if p.is_symlink():ok=False;continue
                            if '__pycache__' in p.parts or '.pytest_cache' in p.parts:continue
                            item=meta(p);item['sha256']=sha(p)
                            member=members.get(rel)
                            if member is None:
                                possible=[m for name,m in members.items() if name.endswith('/'+rel)]
                                member=possible[0] if len(possible)==1 else None
                            item['archive_member']=member.name if member else None
                            item['archive_sha256']=hashlib.file_digest(tf.extractfile(member),'sha256').hexdigest() if member else None
                            item['match']=item['sha256']==item['archive_sha256']
                            ok=ok and item['match'];fs.append(item)
                    if fs:row['subdirs'].append(dict(path=str(d),fully_archived=bool(ok),files=fs))
        except (OSError,tarfile.TarError) as e:row['problems'].append(str(e))
        snapshots.append(row)
    if 'pyvenv.cfg' in files and len(b.relative_to(R).parts)<=2:
        pkgs=[]; special=[]
        for s in b.glob('lib/python*/site-packages'):
            for m in sorted(s.glob('*.dist-info/METADATA')):
                name=version=None
                with m.open(errors='replace') as f:
                    for line in f:
                        if line.startswith('Name: '):name=line[6:].strip()
                        if line.startswith('Version: '):version=line[9:].strip()
                        if name and version:break
                pkgs.append(dict(name=name,version=version))
            for p in [*s.glob('*.pth'),*s.glob('*.egg-link'),*s.glob('*.dist-info/direct_url.json')]:
                special.append(dict(path=str(p),text=p.read_text(errors='replace')))
        environments.append(dict(path=str(b),pyvenv=(b/'pyvenv.cfg').read_text(),packages=pkgs,
                                 links=special,python_realpath=str((b/'bin/python').resolve())))

# Cross-project dependency discovery only: symlink targets and matching code/config lines.
# Do not inspect scientific data, credentials or hidden platform configuration.
for top in Path('/workspace').iterdir():
    if not top.is_dir() or top==R or top.name.startswith('.'):continue
    for base,dirs,files in os.walk(top,followlinks=False):
        b=Path(base)
        dirs[:]=[n for n in dirs if n not in ['.git','node_modules','site-packages','__pycache__','results','data','runtime','models'] and not n.startswith('.venv')]
        for n in dirs+files:
            p=b/n
            if p.is_symlink():
                target=str(p.resolve())
                if target.startswith(str(R)):references.append(dict(path=str(p),kind='symlink',target=target))
            elif p.is_file() and p.suffix in ['.sh','.py','.cfg','.conf','.toml','.pth'] and p.stat().st_size<2_000_000:
                for i,line in enumerate(p.read_text(errors='replace').splitlines(),1):
                    if str(R) in line:
                        matches=re.findall(r'/workspace/mevo_acoustic_microbubbles/[^\s\"\x27,;\)]+',line)
                        references.append(dict(path=str(p),line=i,kind='path_reference',targets=matches))

print(json.dumps(dict(caches=caches,snapshots=snapshots,environments=environments,
                     outside_project_references=references),ensure_ascii=False))
