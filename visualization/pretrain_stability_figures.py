"""共用作图样式：Arial 字体和浅色配色（INK、setup_style）。

原来是 2 s PRETRAIN 稳定性矩阵的解释图和动画脚本（输出在 visualization/pretrain_stability_2s/）。
它读取的旧写法配置（configs/pretrain_feasibility_2s.json、configs/pretrain_stability_2s/）和
workflows.f10ag.context 已于 2026-11-06 删除，作图部分随之删除（用户决定）；生成那些图的版本在
提交 03e0701。只保留 INK 和 setup_style，因为 evidence/ 里 12 份作图脚本从这里导入它们。
"""

import shutil
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager

ARIAL_DIR = Path("/mnt/c/Windows/Fonts")  # WSL 下的 Windows 字体目录，只读加载，不安装
INK = dict(
    primary="#0b0b0b",
    secondary="#52514e",
    muted="#898781",
    grid="#e1e0d9",
    axis="#c3c2b7",
    surface="#fcfcfb",
    track="#f0efec",
)


def setup_style(font_dir):
    """设置 Arial 和浅色图面；返回实际使用的字体名（写入清单）。

    FreeType 绘制时会反复读取字体文件；直接从 /mnt/c（WSL 的 9P 挂载）读极慢，
    所以先把 Arial 复制到本次运行的临时目录 font_dir 再注册。
    """
    family = "DejaVu Sans"
    if (ARIAL_DIR / "arial.ttf").is_file():
        for name in ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"):
            if (ARIAL_DIR / name).is_file():
                local = Path(shutil.copy(ARIAL_DIR / name, font_dir / name))
                font_manager.fontManager.addfont(str(local))
        family = "Arial"
    else:
        print(f"Arial not found under {ARIAL_DIR}; figures use DejaVu Sans")
    plt.rcParams.update(
        {
            "font.family": family,
            "font.size": 9.5,
            "mathtext.fontset": "custom",
            "mathtext.rm": family,
            "mathtext.it": f"{family}:italic",
            "mathtext.bf": f"{family}:bold",
            "mathtext.sf": family,
            "mathtext.cal": family,
            "axes.edgecolor": INK["axis"],
            "axes.labelcolor": INK["secondary"],
            "axes.titlesize": 10.5,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.titlecolor": INK["primary"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.facecolor": INK["surface"],
            "figure.facecolor": INK["surface"],
            "savefig.facecolor": INK["surface"],
            "xtick.color": INK["axis"],
            "ytick.color": INK["axis"],
            "xtick.labelcolor": INK["secondary"],
            "ytick.labelcolor": INK["secondary"],
            "grid.color": INK["grid"],
            "grid.linewidth": 0.6,
            "legend.frameon": False,
            "pdf.fonttype": 42,
        }
    )
    return family
