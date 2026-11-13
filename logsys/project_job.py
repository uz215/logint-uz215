# -*- coding: utf-8 -*-
"""项目内作业执行器：在项目里对某口井跑 QuickLook / 综合解释。

为什么用**子进程**而不是同进程调用
----------------------------------
logInt 的解释流程是重量级的（读 LAS → QC → 岩性 → 沉积相 → 解释 → 出图），
单井常需数分钟。它同时会改写全局状态（``_PLOT_MODE``、``config['output_dir']``、
matplotlib 全局 rcParams），若在同一进程里跑，会污染 GUI 进程并可能崩溃。

因此本模块用**独立子进程**跑 logInt：
  - GUI 线程不被阻塞（后台线程 + 队列回传日志）；
  - 解释流程的全局状态与 GUI 完全隔离；
  - 崩溃/异常不影响浏览器窗口；
  - 产物落盘路径与手工执行完全一致（``output/<井名>/``）。

产物落盘的关键
--------------
logInt 内部用 ``Path('output') / well_name`` 定位产物目录，**相对 CWD**。
所以子进程的 CWD 必须设为**项目根的父目录**，产物才会落回项目树的
``output/<井名>/`` —— 这正是"作业在项目里做、产物回到项目树"的闭环。

⚠️ 井名不一致的坑
-----------------
那个 ``well_name`` 取自 **LAS 的 ~W 段**（读不到时退化为文件名），
并不等于项目内的登记名、也不等于源目录名。例如源目录 ``RP-13`` 里的
LAS 记录井名为 ``RASHIDPUR_13``，产物就会落到 ``output/RASHIDPUR_13/``，
与项目树里的登记井名对不上，闭环断在命名上。

两道防线：
  1. **预防** —— 添加井时读出 LAS 井名并用它作为默认井名；
  2. **兜底** —— 作业结束后由 :func:`align_products` 把产物归集到
     ``output/<项目内井名>/``（重命名或合并），保证闭环成立。

日志回传
--------
子进程 stdout/stderr 被逐行读取，通过回调交给 GUI 写进 Output window
（对应 Techlog 的 Output window）。
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading

#: 作业类型 → (中文名, logInt 命令行参数前缀)
JOB_TYPES = {
    'quicklook': ('快速解释图（Quick Look）', '--quicklook'),
    'comprehensive': ('综合解释', ''),
}


def repo_root() -> str:
    """logInt 仓库根（logsys 的上一级）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def python_exe() -> str:
    """作业用的 Python 解释器。

    **优先项目自带的 .venv**：logInt 的依赖（numpy/pandas/matplotlib/lasio…）
    装在 ``<repo>/.venv``，而 GUI 进程可能由别的解释器（如 IDE/工具链的
    Python）启动，直接用 ``sys.executable`` 会因缺依赖而失败。
    找不到 .venv 时退回当前解释器。
    """
    venv_py = os.path.join(repo_root(), '.venv', 'Scripts', 'python.exe')
    if os.path.isfile(venv_py):
        return venv_py
    venv_py = os.path.join(repo_root(), '.venv', 'bin', 'python')
    if os.path.isfile(venv_py):
        return venv_py
    return sys.executable or 'python'


def build_command(job_type: str, source_dir: str, las_file: str = '',
                  gas_file: str = '', config_file: str = '') -> list[str]:
    """构造作业命令行。

    - ``quicklook``：``python logInt.py --quicklook <井资料目录> [--quicklook-config X]``
      —— logInt 的 ``--quicklook`` 分支会把井目录当第一参数。
    - ``comprehensive``：``python logInt.py <主LAS> [--gas X]``
      —— 走原有综合解释入口（run_well_log_workflow）。

    说明：``--quicklook`` 分支在解析参数时会把**第一个非 - 开头的参数**
    当作井目录，因此参数顺序必须是：``--quicklook <井目录> [其他]``。
    """
    py = python_exe()
    logint = os.path.join(repo_root(), 'logInt.py')
    if not os.path.isfile(logint):
        raise FileNotFoundError('未找到 logInt.py：%s' % logint)

    if job_type == 'quicklook':
        cmd = [py, logint, '--quicklook', str(source_dir)]
        if config_file:
            cmd += ['--quicklook-config', str(config_file)]
        return cmd

    if job_type == 'comprehensive':
        if not las_file:
            raise ValueError('综合解释需要主 LAS 文件')
        cmd = [py, logint, str(las_file)]
        if gas_file:
            cmd += ['--gas', str(gas_file)]
        return cmd

    raise ValueError('未知作业类型: %s' % job_type)


def find_main_las(well_dir: str) -> str:
    """在井目录中找主测井 LAS（根目录优先，排除气测 LAS）。

    与 logInt 的 ``_find_main_las`` 同策略，但独立实现以避免 GUI 模块
    依赖 1 MB 的 logInt.py（GUI 层保持轻量、可单测）。
    """
    if not well_dir or not os.path.isdir(well_dir):
        return ''
    gas_kw = ('gas', 'tgas', 'gastotal', '气测', '录井气', 'gasav')

    def _not_gas(name: str) -> bool:
        low = name.lower()
        if any(k in low for k in gas_kw):
            return False
        return not (low.endswith(('.txt', '.csv', '.xls', '.xlsx', '.dat')))

    root_las = [os.path.join(well_dir, f) for f in os.listdir(well_dir)
                if f.lower().endswith('.las') and _not_gas(f)]
    if root_las:
        root_las.sort(key=lambda p: os.path.getsize(p), reverse=True)
        return root_las[0]
    all_las = []
    for base, _dirs, files in os.walk(well_dir):
        for f in files:
            if f.lower().endswith('.las') and _not_gas(f):
                all_las.append(os.path.join(base, f))
    if not all_las:
        return ''
    all_las.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return all_las[0]


def find_client_format(well_dir: str) -> str:
    """在井目录中找甲方出图格式文件（*_qlpt.json / quicklook_config.json）。"""
    if not well_dir or not os.path.isdir(well_dir):
        return ''
    try:
        cands = []
        for base, _dirs, files in os.walk(well_dir):
            for f in files:
                low = f.lower()
                if low.endswith('.json') and ('qlpt' in low or 'quicklook' in low
                                              or 'format' in low):
                    cands.append(os.path.join(base, f))
    except Exception:
        return ''
    if not cands:
        return ''
    cands.sort(key=lambda p: (0 if os.path.basename(p).lower() == 'quicklook_config.json' else 1,
                               len(p)))
    return cands[0]


def snapshot_products(products_root: str) -> dict:
    """快照产物根下各井目录的"最新文件修改时间"。

    作业前后各取一次，即可识别出**本次作业**新建或更新了哪些井目录 ——
    这是把产物归集到正确井目录的依据。
    """
    out: dict[str, float] = {}
    try:
        entries = os.listdir(products_root)
    except OSError:
        return out
    for e in entries:
        d = os.path.join(products_root, e)
        if not os.path.isdir(d):
            continue
        newest = 0.0
        for dirpath, _dirs, files in os.walk(d):
            for fn in files:
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(dirpath, fn)))
                except OSError:
                    pass
        out[e] = newest
    return out


def align_products(products_root: str, well_name: str,
                   before: dict | None = None,
                   on_error=None) -> list[str]:
    """把本次作业的产物归集到 ``output/<项目内井名>/``。

    产物目录名由 LAS 井名决定，可能与项目内登记名不同（见模块文档）。
    这里在作业结束后做一次归集：
      - 目标目录不存在 → 直接**重命名**（同盘，原子、零拷贝）；
      - 目标目录已存在 → 把新文件**合并**进去（同名覆盖）；
      - 源目录合并后为空 → 删掉，避免项目树里留下幽灵井。

    ``before`` 必须是**子进程启动之前**的产物快照，否则新建的产物目录
    会被当成"作业前就存在的"，认不出来（见 :meth:`JobRunner.start`）。

    返回被归集（合并/重命名）过的源目录名列表；失败原因经 ``on_error``
    回调反馈（不静默吞掉 —— 静默会让"产物没回项目树"变成无迹可寻的谜）。
    """
    name = str(well_name or '').strip()
    if not name or not os.path.isdir(products_root):
        return []
    before = before or {}
    now = snapshot_products(products_root)
    changed = [d for d, t in now.items()
               if d != name and (d not in before or before.get(d) != t)]
    moved = []
    for d in changed:
        src = os.path.join(products_root, d)
        dst = os.path.join(products_root, name)
        if not os.path.isdir(src):
            continue
        try:
            if not os.path.isdir(dst):
                os.replace(src, dst)
                moved.append(d)
            else:
                merged = _merge_dir(src, dst)
                if merged:
                    moved.append(d)
                if os.path.isdir(src) and not _remove_empty_dir(src):
                    if on_error:
                        on_error('归集后源目录仍非空，未删除：%s' % src)
        except OSError as e:
            if on_error:
                on_error('产物归集失败 %s → %s：%s' % (d, name, e))
            continue
    return moved


def _merge_dir(src: str, dst: str) -> bool:
    """把 src 下的文件合并进 dst（同名覆盖）。返回是否搬动了文件。

    合并后 src 里可能剩下**空子目录**（如 crossplots/），也要一并清掉，
    否则源目录非空 → 删不掉 → 项目树里留下一个幽灵井。
    """
    moved = False
    for dirpath, _dirs, files in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        target_dir = dst if rel == '.' else os.path.join(dst, rel)
        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError:
            continue
        for fn in files:
            s = os.path.join(dirpath, fn)
            t = os.path.join(target_dir, fn)
            try:
                if os.path.isfile(t):
                    os.remove(t)
                os.replace(s, t)
                moved = True
            except OSError:
                continue
    # 清掉 src 下残留的空目录（含嵌套）
    for dirpath, dirs, files in os.walk(src, topdown=False):
        if dirpath == src:
            continue
        if not dirs and not files:
            try:
                os.rmdir(dirpath)
            except OSError:
                pass
    return moved


def _remove_empty_dir(path: str) -> bool:
    """删除空目录。已删除返回 True；非空或失败返回 False。"""
    try:
        if os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)
            return True
    except OSError:
        pass
    return False


class JobRunner:
    """后台作业执行器：子进程跑 logInt，日志逐行回传。

    用法::

        runner = JobRunner(on_log=cb, on_done=cb2)
        runner.start('quicklook', source_dir, project_root)
        runner.is_running()   # → True
    """

    def __init__(self, on_log=None, on_done=None):
        self.on_log = on_log
        self.on_done = on_done
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._cancel = False

    # ------------------------------------------------------------------ 状态
    @property
    def thread(self):
        """作业线程（供调用方 join —— daemon 线程被强杀会留下半截产物）。"""
        return self._thread

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def cancel(self):
        """请求中止当前作业（终止子进程）。"""
        with self._lock:
            self._cancel = True
            proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    # ------------------------------------------------------------------ 执行
    def start(self, job_type: str, source_dir: str, project_root: str,
              las_file: str = '', gas_file: str = '', config_file: str = '',
              well_name: str = '') -> bool:
        """启动作业。返回 False 表示启动失败（原因经 on_log 反馈）。

        ``well_name`` 是**项目内登记的井名**，产物归集时用它作为目标目录
        （LAS 里的井名可能与之不同）。
        """
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                self._emit('已有作业在运行，已忽略本次请求')
                return False

        if job_type == 'quicklook' and not config_file:
            config_file = find_client_format(source_dir)
        if job_type == 'comprehensive' and not las_file:
            las_file = find_main_las(source_dir)

        try:
            cmd = build_command(job_type, source_dir, las_file, gas_file, config_file)
        except Exception as e:
            self._emit('作业启动失败：%s' % e)
            self._finish(1, '')
            return False

        # 产物目录 Path('output')/井名 相对 CWD → CWD 取项目根的父目录
        cwd = os.path.dirname(os.path.abspath(project_root)) or os.getcwd()
        label = JOB_TYPES.get(job_type, (job_type, ''))[0]
        self._emit('▶ 开始%s：%s' % (label, source_dir))
        self._emit('  命令：%s' % ' '.join(cmd))
        self._emit('  工作目录：%s（产物落回 %s）' % (cwd, project_root))

        # 【关键时序】产物快照必须在**子进程启动之前**取。
        # 解释流程一开始就会创建 output/<LAS井名>/ 目录，若快照取得晚了，
        # 快照里就会带上"本次作业新建的目录"，归集时便认不出它，
        # 结果产物留在错名的目录里回不到项目树。
        before = snapshot_products(project_root) if project_root else {}

        env = dict(os.environ)
        env['PYTHONIOENCODING'] = 'utf-8'
        env.setdefault('PYTHONUNBUFFERED', '1')
        # 非交互：避免 logInt 的依赖检查/对话框在无 stdin 的子进程里阻塞
        env['LOGINT_NONINTERACTIVE'] = '1'

        try:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, text=True,
                                    encoding='utf-8', errors='replace')
        except Exception as e:
            self._emit('作业启动失败：%s' % e)
            self._finish(1, '')
            return False

        with self._lock:
            self._proc = proc
            self._cancel = False
        self._thread = threading.Thread(
            target=self._pump,
            args=(proc, label, project_root,
                  well_name or os.path.basename(os.path.abspath(source_dir)),
                  before),
            daemon=True)
        self._thread.start()
        return True

    def _pump(self, proc: subprocess.Popen, label: str,
              project_root: str = '', well_name: str = '', before: dict | None = None):
        """逐行读取子进程输出 → 回调。"""
        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    line = line.rstrip('\r\n')
                    if line:
                        self._emit(line)
        except Exception as e:
            self._emit('日志读取中断：%s' % e)
        code = proc.wait()
        with self._lock:
            cancelled = self._cancel
        if cancelled:
            self._emit('■ %s 已取消' % label)
        elif code == 0:
            self._emit('■ %s 完成' % label)
        else:
            self._emit('■ %s 结束（退出码 %d）' % (label, code))
        # 产物归集：LAS 井名与项目登记名不一致时，把产物挪回本井目录。
        # 【顺序很关键】必须**在** `self._proc = None` 与 `_finish()` **之前**：
        # 这两步一做，调用方（CLI 的等待循环、GUI 的按钮状态）就认为作业结束；
        # 而本线程是 daemon 线程，调用方一退出进程，这里就被强行终止 ——
        # 归集做一半，产物就留在错名的目录里回不到项目树。
        if project_root and well_name and code == 0:
            try:
                moved = align_products(project_root, well_name, before,
                                        on_error=self._emit)
                if moved:
                    self._emit('↳ 产物已归集到 output/%s/（原目录：%s）'
                               % (well_name, '；'.join(moved)))
            except Exception as e:
                self._emit('产物归集失败（不影响作业结果）：%s' % e)
        with self._lock:
            self._proc = None
        self._finish(code, label)

    def _emit(self, msg: str):
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                pass

    def _finish(self, code: int, label: str):
        if self.on_done:
            try:
                self.on_done(code, label)
            except Exception:
                pass


if __name__ == '__main__':
    import argparse
    import sys as _sys
    import time

    # 支持 `python logsys/project_job.py` 直接运行（包路径不在 sys.path 时）
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from logsys import project_config as pcfg

    ap = argparse.ArgumentParser(description='项目作业执行器（自检）')
    ap.add_argument('--root', default=os.path.join(repo_root(), 'output'))
    ap.add_argument('--well', default='')
    ap.add_argument('--job', default='quicklook', choices=list(JOB_TYPES))
    args = ap.parse_args()

    _r = JobRunner(on_log=lambda m: print(m, flush=True),
                   on_done=lambda c, l: print('=== DONE code=%s label=%s ===' % (c, l),
                                              flush=True))
    # 成员清单 = 已登记的井 ∪ 产物目录子目录（光扫目录会漏掉"刚添加、
    # 尚无产物"的井 —— 那正是最需要跑作业的那批）
    _names = [args.well] if args.well else pcfg.project_member_names(args.root)
    _sm = pcfg.source_map(args.root, _names)
    for _n in _names:
        _src = _sm.get(_n)
        if not _src:
            print('跳过 %s（无源目录）' % _n, flush=True)
            continue
        print('=== %s → %s' % (_n, _src), flush=True)
        # well_name 传项目内登记名：产物目录名由 LAS 井名决定，两者不一致时
        # 作业结束后由 align_products 归集回来
        _r.start(args.job, _src, args.root, well_name=_n)
        while _r.is_running():
            time.sleep(0.3)
        # 作业线程还要做产物归集，等它真正收尾（daemon 线程被强杀会留下半截产物）
        if _r.thread:
            _r.thread.join(timeout=30)
        break
