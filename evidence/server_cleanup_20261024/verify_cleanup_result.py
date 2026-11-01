"""Verify exact deletion boundaries, preserved content, and write completion evidence."""
from pathlib import Path
import gzip,json,hashlib,subprocess,datetime,collections
E=Path(__file__).resolve().parent;X=E/'execution_A1_A2_B1_B4';ROOT=E.parents[1]
def gz(p):return json.load(gzip.open(p,'rt'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
P=json.loads((E/'CANDIDATES.json').read_text());A=json.loads((X/'AUTHORIZATION.json').read_text())
B=json.loads((E/'LOCAL_BASELINE.json').read_text())
before=gz(X/'PRE_INVENTORY.json.gz');after=gz(X/'POST_INVENTORY.json.gz')
events=[json.loads(l) for name in ['DELETE_JOURNAL.jsonl','DELETE_RESUME_JOURNAL.jsonl'] for l in (X/name).read_text().splitlines()]
deleted=[e for e in events if e['event']=='deleted'];done={e['path'] for e in deleted}
approved={t['path'] for g in P['groups'] if g['id'] in A['approved_groups'] for t in g['targets']}
root=Path(P['root']);pre={str(root/r['path']):r for r in before['rows']};post={str(root/r['path']):r for r in after['rows']}
def under(path,targets):
    p=Path(path)
    return any(str(q) in targets for q in [p,*p.parents])
expected_removed={p for p in pre if under(p,approved)}
actual_removed=pre.keys()-post.keys()
unexpected_removed=sorted(actual_removed-expected_removed)
not_removed=sorted(expected_removed-actual_removed)
ancestors={str(a) for p in approved for a in Path(p).parents}
changes=[]
fields=['kind','bytes','mtime_ns','inode','dev','nlink','mode','target']
for p in pre.keys()&post.keys():
    a,b=pre[p],post[p]
    keys=['kind','inode','dev','mode'] if p in ancestors and a['kind']=='directory' else fields
    diff=[k for k in keys if a.get(k)!=b.get(k)]
    if diff:changes.append(dict(path=p,fields=diff))
new_paths=sorted(post.keys()-pre.keys())
a3=[r for r in gz(E/'CANDIDATE_ENTRY_IDENTITIES.json.gz') if r['group']=='A3']
a3_changes=[]
for r in a3:
    p=str(root/r['path'])
    if p not in post or any(r.get(k)!=post[p].get(k) for k in fields):a3_changes.append(p)
changed_local=[]
for key in ['tracked_sha256','code_sha256']:
    for name,h in B[key].items():
        p=ROOT/name
        if not p.is_file() or sha(p)!=h:changed_local.append(name)
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
content=json.loads((X/'POST_CONTENT.json').read_text());local_check=json.loads((X/'LOCAL_INPUT_CHECK.json').read_text())
disk_before=next(e for e in events if e['event']=='disk_before')
disk_after=next(e for e in reversed(events) if e['event']=='complete')
before_bytes=int(disk_before['du']['stdout'].split()[0]);after_bytes=int(disk_after['du']['stdout'].split()[0])
passed=(done==approved and len(done)==len(deleted) and not unexpected_removed and not not_removed and not changes and not a3_changes and not new_paths and not changed_local and head==B['head'] and before['git_roots']==after['git_roots'] and before['supervisor']==after['supervisor'] and before['activation']==after['activation'] and content['status']=='PASS' and local_check['status']=='PASS' and not after['errors'])
summary=dict(status='PASS' if passed else 'FAIL',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    approved_groups=A['approved_groups'],excluded_group='A3',deleted_targets=len(deleted),
    deleted_directories=sum(d['type']=='directory' for d in deleted),deleted_symlinks=sum(d['type']=='symlink_only' for d in deleted),
    actual_deleted_entries=len(actual_removed),unexpected_removed=unexpected_removed,approved_entries_not_removed=not_removed,
    preserved_entry_changes=changes,new_paths=new_paths,a3_preserved_entries=len(a3),a3_changes=a3_changes,
    protected_remote_files_verified=len(content['protected_files']),retained_F10AG_import_check=content['retained_F10AG_import_check'],
    local_inputs_verified=local_check['verified_inputs'],changed_local_baseline=changed_local,head_before=B['head'],head_after=head,
    remote_git_unchanged=before['git_roots']==after['git_roots'],supervisor_unchanged=before['supervisor']==after['supervisor'],activation_unchanged=before['activation']==after['activation'],
    before_allocated_bytes=before_bytes,after_allocated_bytes=after_bytes,reclaimed_allocated_bytes=before_bytes-after_bytes,
    candidate_allocated_bytes=sum(d['allocated_bytes'] for d in deleted),
    interruption='TensorBoard read-only directory scan outside deletion targets; process untouched; remaining B3/B4 rechecked and completed.',
    no_simulation_or_service_restart=True,git_commit_or_push=False,
    groups=[dict(id=g['id'],deleted_targets=sum(e['group']==g['id'] for e in deleted),allocated_bytes=sum(e['allocated_bytes'] for e in deleted if e['group']==g['id'])) for g in P['groups'] if g['id'] in A['approved_groups']])
(X/'RESULT_VALIDATION.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:summary[k] for k in ['status','deleted_targets','deleted_directories','deleted_symlinks','actual_deleted_entries','unexpected_removed','approved_entries_not_removed','preserved_entry_changes','new_paths','a3_changes','changed_local_baseline','reclaimed_allocated_bytes']},ensure_ascii=False,indent=2))
if not passed:raise SystemExit(1)

ref='../evidence/server_cleanup_20261024/execution_A1_A2_B1_B4/'
report=ROOT/'docs/SERVER_CLEANUP_RESULT_20261024.md'
text=f'''# 微泡聚集仿真：服务器清理执行结果

日期：2026-10-24。状态：**已完成；执行后校验 PASS。**

用户批准：“批准 A1–A2、B1–B4”。对应原清单 SHA-256：`{A['manifest_sha256']}`。
服务器：`root@95.3.33.46:15283`；范围：`/workspace/mevo_acoustic_microbubbles/`。

## 已执行范围

共删除 **{len(deleted)} 个清单条目**：{summary['deleted_directories']} 个目录、{summary['deleted_symlinks']} 个指向已退役环境的快捷链接。所有获批条目均完成，没有扩大范围。

| 分组 | 对象 | 条目数 | 原占用 |
|---|---|---:|---:|
'''
for g in summary['groups']:
    title=next(x['title'] for x in P['groups'] if x['id']==g['id'])
    text+=f'| {g["id"]} | {title} | {g["deleted_targets"]} | {g["allocated_bytes"]/2**20:.2f} MiB |\n'
text+=f'''
**A3 未获批准，315 个源码展开目录全部保留。** 四套旧环境 B1–B4 及对应快捷链接已退役；以后重跑相应历史任务需要重新建立环境。其科研数据、源码和日志仍在。

## 实际空间变化

| 测量 | 分配空间 |
|---|---:|
| 执行前项目目录 | {before_bytes:,} B（{before_bytes/2**30:.3f} GiB） |
| 执行后项目目录 | {after_bytes:,} B（{after_bytes/2**30:.3f} GiB） |
| 实际减少 | **{before_bytes-after_bytes:,} B（{(before_bytes-after_bytes)/2**30:.3f} GiB）** |

按删除前后 `du -sx -B1` 实测。与清单逐项估计略有差异，是父目录自身分配空间也随删除发生变化；记录中保留了两次 `df` 原始输出。本次释放的是服务器空间，本地 WSL 数据没有删除。

## 保留与验证

- 对比服务器执行前后完整目录元信息：除批准范围以及其父目录必要的目录元信息变化外，没有额外删除、新文件或保留文件变化。
- A3 的 {len(a3):,} 个目录、文件及链接条目元信息全部一致。
- 59 个已登记科研文件，执行前后大小与 SHA-256 全部匹配，包括关键轨迹、声场和输入数据。
- 主环境、F10AA 共享环境、F10AG 环境、渲染环境、共享 Python、APECSS、F10AF 声场及跨项目依赖保留。
- F10AG 环境实际导入 NumPy、SciPy、h5py、OSQP 通过；本地独立工程导入和 20 个固定输入检查通过。没有启动数值仿真或 GPU 测试。
- 三处服务器 Git 工作树、Supervisor 配置及激活入口保持一致；本地原有跟踪文件和执行代码哈希不变，HEAD 仍为 `{head}`。
- 实物实验、BraVa、血栓及其他项目不在删除范围；没有停止后台进程、修改服务或提交、推送 Git。

执行期间的保护检查曾因 TensorBoard 短暂打开保留结果目录而暂停。核查确认这是候选目录之外的只读目录扫描，不依赖待退役环境；没有停止 TensorBoard。收窄为“保留只读目录扫描不阻止无关候选清理”后，重新核查 B3、B4 的全部内容、Git、运行依赖和保护文件，完成剩余删除。第一次暂停及续执行日志均保留。

## 证据

- [原始审核报告](SERVER_CLEANUP_AUDIT_20261024.md) 与 [逐项原始路径清单](../evidence/server_cleanup_20261024/CANDIDATE_PATHS.txt)。原审核报告保持为批准前快照，本文件记录其后实际执行状态。
- [用户授权与清单身份]({ref}AUTHORIZATION.json)。
- [执行及保留范围验证]({ref}RESULT_VALIDATION.json)。
- [首次删除日志]({ref}DELETE_JOURNAL.jsonl)、[剩余删除日志]({ref}DELETE_RESUME_JOURNAL.jsonl)。
- [科研文件与保留环境检查]({ref}POST_CONTENT.json)、[本地输入检查]({ref}LOCAL_INPUT_CHECK.json)。
- `PRE_INVENTORY.json.gz`、`POST_INVENTORY.json.gz`：完整执行前后目录元信息。
- [执行证据 SHA-256]({ref}SHA256SUMS.txt)。
'''
report.write_text(text)
files=sorted(p for p in X.iterdir() if p.is_file() and p.name!='SHA256SUMS.txt')+[report]+[E/n for n in ['capture_execution_checks.py','run_approved_cleanup.py','remote_execute_approved.py','resume_approved_cleanup.py','check_preserved_content.py','verify_cleanup_result.py']]
(X/'SHA256SUMS.txt').write_text(''.join(f'{sha(p)}  {p.relative_to(ROOT)}\n' for p in files))
print('Report:',report)
