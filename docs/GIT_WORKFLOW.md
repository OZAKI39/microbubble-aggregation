# 一个工程、一个工作树

固定在 `/home/lzy/projects/new_microbubble_aggregation` 开发。当前分支
`main`，不因每次修改创建日期分支；从原重构分支改名，提交历史不变。
本地是独立 Git 历史；旧 GitHub 快照的子目录结构不能直接当作本项目的远程根目录。

## 已确认的远程

用户于2026-10-22选择独立仓库。公开仓库为
`https://github.com/OZAKI39/microbubble-aggregation`，配置为本目录的 `origin`；
本地和 GitHub 发布分支固定为 `main`。2026-11-01 首次同步的内容边界与检查记录见
[GitHub 同步范围](GITHUB_SYNC.md)。
旧 GitHub 同步分支保留。下表保留选择依据，后续默认采用 A。

| 方案 | 日常复杂度 | 对旧仓库的影响 |
|---|---|---|
| A：独立仓库，例如 `OZAKI39/microbubble-aggregation` | 最简单；项目根目录直接对应远程根目录，稳定 `main` 分支 | 旧同步分支原样保留；无需合并不相关历史。推荐 |
| B：原仓库的新专用分支，例如 `microbubble-aggregation` | 同样从当前工作树直接 push，但与旧主线无共同历史，网页默认分支和 PR 容易混淆 | 只创建专用分支，禁止覆盖 main 或任何旧同步分支；不得尝试把独立根目录强推到旧分支 |

不需要第二个本地推送目录，不复制工程或重写提交。已配置本地 `push.default=simple`。

## 日常提交

```bash
cd /home/lzy/projects/new_microbubble_aggregation
git status --short
git diff
git add microbubble/需要提交的文件.py tests/对应测试.py
git diff --cached --stat
git diff --cached
git commit -m "Describe the actual change"
# 首次明确要求推送时，建立 upstream：
git push -u origin main
# 此后每次明确要求推送时：
git push
```

上面的文件名是示例，按本次实际改动逐项暂存。提交和推送是分别授权的操作。
不能习惯性使用 `git add -A`、`push --force`、`reset --hard` 或 `clean -fdx`。

## 科研文件

- 跟踪源码、配置、测试、`inputs/` 必要响应/声场和轻量科研证据。
- `results/` 不再整体隐藏：执行身份、摘要、失败状态、图、未知新输出均在 status 中可见，审查后决定是否提交。
- 完整逐步轨迹、逐步 Gate/力记录按明确文件用途忽略，保留本地原件；已有结果身份见 `evidence/migration/NEW_RESULT_MANIFEST.json`。忽略不等于备份，也不授权删除。
- 新正式大数据记录路径、大小、SHA-256、生成配置/提交、是否存在经核验的另一份副本及恢复方法；只有远程路径记录时写明未验证。
- `scratch/`、`results/_scratch/`、`results/_render_frames/` 专供可再生临时内容，不存唯一证据。
- 现有已跟踪文件本次不取消跟踪、不改写历史；`.gitignore` 也不会移除旧提交中的大对象。

历史 `evidence/` 中的同步清单用于溯源，不能把其中旧 export/clone 流程当成后续开发指令。
