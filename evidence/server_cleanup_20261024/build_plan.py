"""Build an explicit approval manifest from read-only evidence. Never deletes remotely."""
from pathlib import Path
import gzip,json,hashlib,collections

E=Path(__file__).resolve().parent
I=json.load(gzip.open(E/'REMOTE_INVENTORY.json.gz','rt'))
D=json.load(gzip.open(E/'REMOTE_DETAIL.json.gz','rt'))
REF=json.load(gzip.open(E/'REFERENCE_EVIDENCE.json.gz','rt'))
R=Path(I['root'])
groups={}
def group(key,title,reason,impact):
    groups[key]=dict(id=key,title=title,reason=reason,impact=impact,targets=[])
def add(key,path,**proof):
    groups[key]['targets'].append(dict(path=str(path),**proof))

group('A1','未完成的空安装环境','无已安装发行包；正式 F10AE 环境另存。','移除失败安装留下的目录；不删除其安装失败日志。')
add('A1',R/'f10ae_target_20261019/.venv_incomplete_download',type='directory')
group('A3','已有完整压缩包的历史源码展开副本','逐文件 SHA 与同快照 source.tar.gz 相符；保留原压缩包、run.sh、SOURCE_*、所有数据及最新 F10AG。','对应历史任务再次执行前需从保留的 source.tar.gz 恢复这些源码子目录。不能直接重启旧 Supervisor 任务。')
archive_dirs=[]
unsafe_cache_dirs=[c['path'] for c in D['caches'] if not c['eligible']]
for s in D['snapshots']:
    if Path(s['directory']).relative_to(R).parts[0]=='f10ag_capture_20261019':continue
    for d in s['subdirs']:
        if not d['fully_archived']:continue
        path=d['path']
        if any(c==path or c.startswith(path+'/') for c in unsafe_cache_dirs):continue
        incoming=[x for x in REF['cross_stage_references'] if x['target']==path or x['target'].startswith(path+'/')]
        incoming += [x for x in I['links'] if x['resolved']==path or x['resolved'].startswith(path+'/')]
        if incoming:continue
        archive_dirs.append(path)
        add('A3',path,type='directory',archive=s['archive']['path'],
            archive_sha256=s['archive_sha256'],verified_source_files=len(d['files']))

group('A2','有源文件的 Python/测试缓存','仅独属仿真阶段的明确缓存；缺少 .py 对应的目录及含其他文件的 __pycache__ 不纳入。','再次运行可能重新编译；不改源文件或科研数据。与 A3 路径互斥。')
for c in D['caches']:
    p=Path(c['path']); parts=p.relative_to(R).parts
    if not c['eligible'] or not parts[0].startswith('f') or parts[0]=='f7':continue
    if any(x.startswith('.venv') or x in ['.python','.postvenv','.git'] for x in parts):continue
    if any(str(p)==d or str(p).startswith(d+'/') for d in archive_dirs):continue
    add('A2',p,type='directory',cache_kind=p.name,verified_files=len(c['files']))

envs=[('B1','F10AB 旧绘图环境','f10ab_shape_20261018/.postvenv'),
      ('B2','F10AC/AD 旧搜索环境','f10ac_ad_20261018/.venv'),
      ('B3','F10AE 旧优化环境','f10ae_target_20261019/.venv'),
      ('B4','F10AF 旧探索环境','f10af_observable_20261019/.venv')]
for key,title,rel in envs:
    group(key,title,'不是当前本地独立工程的环境，也不是服务器 F10AG 的独立环境；包名/版本/解释器及路径引用已保存。',
          '可选退役：相应旧阶段不能直接重跑，需按保存版本重新安装；当前未做重建成功保证。仅删除列出的环境和指向它的历史快捷链接，不替换其他环境。')
    p=R/rel; add(key,p,type='directory')
    for link in I['links']:
        q=R/link['path']
        if link['resolved']==str(p) and not str(q).startswith(str(p)+'/'):
            add(key,q,type='symlink_only',target=link['target'])

index={}
for g in groups.values():
    for t in g['targets']:
        assert str(Path(t['path'])).startswith(str(R)+'/')
        assert t['path'] not in index
        t.update(apparent_bytes=0,allocated_bytes=0,files=0,entries=0)
        index[t['path']]=(g['id'],t)
ordered=sorted(index)
for i,p in enumerate(ordered):
    assert not (i and p.startswith(ordered[i-1]+'/')),('overlap',p,ordered[i-1])
exact=[]
for row in I['rows']:
    p=R/row['path']; target=None
    for a in [p,*p.parents]:
        if str(a) in index:target=index[str(a)];break
        if a==R:break
    if target is None:continue
    key,t=target
    t['entries']+=1;t['allocated_bytes']+=row['allocated_bytes']
    if row['kind']=='file':t['files']+=1;t['apparent_bytes']+=row['bytes']
    if str(p)==t['path']:t['identity']={k:row[k] for k in ['mode','dev','inode','mtime_ns','nlink']}
    exact.append(dict(group=key,candidate_target=t['path'],**row))
for g in groups.values():
    g['allocated_bytes']=sum(t['allocated_bytes'] for t in g['targets'])
    g['apparent_bytes']=sum(t['apparent_bytes'] for t in g['targets'])
    g['files']=sum(t['files'] for t in g['targets'])
    g['directories']=sum(t['type']=='directory' for t in g['targets'])
    g['symlinks']=sum(t['type']=='symlink_only' for t in g['targets'])
plan=dict(status='AWAITING_USER_CONFIRMATION_NO_DELETION',date='2026-10-24',server='root@95.3.33.46:15283',
          root=str(R),local_authority='/home/lzy/projects/new_microbubble_aggregation',
          groups=[groups[k] for k in sorted(groups)],
          total_allocated_bytes=sum(g['allocated_bytes'] for g in groups.values()),
          rules=['Exact listed paths only; no glob execution.',
                 'Recheck processes, metadata, archive SHA and references immediately before deletion; skip changed items.',
                 'Never follow directory symlinks; never remove results, scientific logs, source.tar.gz, Git or protected dependencies.',
                 'No Supervisor restart/update, no push or code/environment changes during this audit.'])
(E/'CANDIDATES.json').write_text(json.dumps(plan,indent=2,ensure_ascii=False))
with gzip.open(E/'CANDIDATE_ENTRY_IDENTITIES.json.gz','wt') as f:json.dump(exact,f)
lines=['# Exact reviewed targets; NO deletion has been approved or executed.']
for key in sorted(groups):
    lines+=['',f'[{key}] {groups[key]["title"]}']
    lines += [t['path']+(' [unlink only]' if t['type']=='symlink_only' else '') for t in groups[key]['targets']]
(E/'CANDIDATE_PATHS.txt').write_text('\n'.join(lines)+'\n')
print(json.dumps([{k:g[k] for k in ['id','title','allocated_bytes','files','directories','symlinks']} for g in plan['groups']],indent=2,ensure_ascii=False))
