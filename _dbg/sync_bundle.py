#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_bundle.py  ——  F:/360/src  ↔  G:/360/src  离线同步助手

适用场景
--------
一端(局域网 F:)连不上 GitHub，另一端(外网 G:)能连；或两端都离线。
用 git bundle 作"离线摆渡载体"：把 .bundle 文件通过 U盘 / 网盘 / 共享文件夹 /
微信文件 等任意通道搬运过去，再在另一端合入。GitHub 仅作中枢/异地备份。

前置条件（本次已一次性完成）
----------------------------
两端已通过"历史焊接"建立共同祖先（提交 4f40a85，两端 sync/latest 已对齐）。
之后日常同步即可用本脚本做正常的增量合并，不再需要文件级复制。

用法（在仓库根目录运行，当前目录即被同步的仓库）
------------------------------------------------
1) 本端有新提交，生成离线包：
       python _dbg/sync_bundle.py export --out g_to_f_20261102.bundle
   包生成后，把它搬运到对端机器。

2) 对端拿到包后，在【对端仓库根目录】合入：
       python _dbg/sync_bundle.py import --bundle g_to_f_20261102.bundle
   合入后 import 会自动把 sync/latest 前移到当前 HEAD，完成一次对齐。

3) 若对端也有新提交，在对端再 export、本端再 import，形成闭环。

说明
----
* 采用"每次打包整条分支 HEAD"的稳健策略（仓库仅数 MB，体积可忽略），
  git 在接收端会自动去重，无需处理增量范围的边界情况。
* 全程 --no-tags，规避指向缺失对象的损坏 tag（如已删除的 v0.2-reg-rashidpur）。
* sync/latest 标签记录"两端已知共享的最新点"，仅在 import 成功后前移，
  保证即使某个包在运输中丢失，下一次有提交的导出也会把缺失提交重新送达。
"""
import argparse
import os
import subprocess
import sys

REPO = os.getcwd()          # 在当前仓库根目录运行
SYNC_REF = "sync/latest"


def sh(cmd, check=True):
    """执行 git 命令，返回 stdout；check=False 时返回 (rc, out, err)。"""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=REPO)
    if check and r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit(f"[FAIL] 命令失败: {cmd}\n{r.stderr}")
    return r


def cur_branch():
    return sh("git rev-parse --abbrev-ref HEAD").stdout.strip()


def is_clean():
    """工作树是否有未提交的已跟踪改动（会影响 merge）。"""
    r = sh("git status --porcelain", check=False)
    # 仅看已跟踪文件的改动（M/A/D/R/C），未跟踪(??)忽略
    for line in r.stdout.splitlines():
        if line[:2] != "??":
            return False
    return True


def cmd_export(out):
    br = cur_branch()
    print(f"[*] 当前分支: {br}")
    print(f"[*] 生成整条分支的离线包（git 接收端会自动去重）...")
    # bundle 仅打包指定分支可达对象，损坏 tag 不会被包含；--no-tags 对 bundle create 无效故省略
    sh(f'git bundle create "{out}" {br}')
    size = os.path.getsize(out)
    print(f"[OK] 已生成: {out}  ({size // 1024} KB)")
    print(f"[NEXT] 把该文件搬运到对端，在【对端仓库根目录】运行:")
    print(f"      python _dbg/sync_bundle.py import --bundle {os.path.basename(out)}")


def cmd_import(bundle):
    if not os.path.exists(bundle):
        raise SystemExit(f"[FAIL] 找不到 bundle 文件: {bundle}")
    if not is_clean():
        raise SystemExit(
            "[FAIL] 当前工作树有未提交的已跟踪改动，先 commit 或 stash 再导入，"
            "避免 merge 覆盖本地工作。\n       提示: git stash / git commit"
        )
    print(f"[*] 校验 bundle: {bundle}")
    sh(f'git bundle verify "{bundle}"')
    br = cur_branch()
    print(f"[*] 从 bundle 拉取内容到本端分支 {br} ...")
    sh(f'git fetch --no-tags "{bundle}" {br}')
    print("[*] 尝试合并（优先快进）...")
    r = sh("git merge --ff-only FETCH_HEAD", check=False)
    if r.returncode != 0:
        print("[*] 不能快进（两端都有新提交），改用普通三方合并...")
        sh("git merge FETCH_HEAD")
    print(f"[*] 更新同步点 {SYNC_REF} -> HEAD")
    sh(f"git tag -f {SYNC_REF} HEAD")
    head = sh("git rev-parse HEAD").stdout.strip()[:12]
    print(f"[OK] 导入完成。本端现处于: {head}")
    print(f"[NEXT] 若本端也有新提交，继续 export 把增量回传对端，形成闭环。")


def main():
    p = argparse.ArgumentParser(description="F:/G: 离线 bundle 同步助手")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="导出本端整条分支到一个 .bundle 文件")
    e.add_argument("--out", required=True, help="输出 bundle 文件路径")
    i = sub.add_parser("import", help="从对端的 .bundle 文件合入本端")
    i.add_argument("--bundle", required=True, help="bundle 文件路径")
    args = p.parse_args()
    if args.cmd == "export":
        cmd_export(args.out)
    else:
        cmd_import(args.bundle)


if __name__ == "__main__":
    main()
