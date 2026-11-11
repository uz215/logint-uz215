# -*- coding: utf-8 -*-
"""门禁：扫描"函数内局部 import 遮蔽模块名、但更早处已引用"的隐患。

【R58 建档背景】1-SPS-108 全判泥岩的最深根因就是这一类：
    run_workflow 内 13950 行写 np.asarray(...)，
    而 import numpy as np 在该方法内位于 14588 行。
Python 编译期即把 np 判定为函数局部变量 → 13950 行必抛
UnboundLocalError → 被外层 except 吞成"不影响主流程"告警 →
整段剖面预判被静默跳过 → 识别器永远拿 'mixed'。
这类 bug 静态可查、运行时却只表现为"某功能悄悄不生效"，必须门禁化。

用法：
    python _dbg/check_local_import_shadow.py            # 扫全仓库 .py
    python _dbg/check_local_import_shadow.py logInt.py  # 只扫指定文件
退出码：0=干净，1=发现隐患（可用于 CI / 出图前门禁）
"""
import ast
import os
import sys

# 需要重点关注被遮蔽的模块别名
WATCH = {'np', 'pd', 'plt', 'os', 're', 'json', 'math', 'time',
         'datetime', 'sys', 'glob', 'shutil', 'copy',
         'numpy', 'pandas', 'matplotlib'}


def _local_import_lines(fn_node):
    """收集函数内(不含嵌套函数体)的 import 绑定名 → 首次导入行号。"""
    found = {}
    stack = list(fn_node.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.Lambda)):
            continue                     # 嵌套函数有自己的作用域
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                bound = a.asname or (a.name.split('.')[0]
                                     if isinstance(node, ast.Import)
                                     else a.name)
                if bound and bound not in found:
                    found[bound] = node.lineno
        for child in ast.iter_child_nodes(node):
            stack.append(child)
    return found


def _loads(fn_node):
    """收集函数内(不含嵌套函数体)的 Name 读取节点。"""
    out = []
    stack = list(fn_node.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.Lambda)):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            out.append((node.lineno, node.id))
        for child in ast.iter_child_nodes(node):
            stack.append(child)
    return out


def scan_file(path):
    try:
        src = open(path, encoding='utf-8', errors='ignore').read()
        tree = ast.parse(src)
    except SyntaxError as e:
        return [('SYNTAX', path, e.lineno or 0, '', 0)]
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        local_imp = _local_import_lines(node)
        if not local_imp:
            continue
        for ln, name in _loads(node):
            if name in WATCH and name in local_imp and ln < local_imp[name]:
                hits.append((node.name, path, ln, name, local_imp[name]))
    return hits


def main(argv):
    targets = argv[1:]
    if not targets:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        targets = []
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns
                      if d not in ('.git', '__pycache__', '_dbg',
                                   'output', 'node_modules')]
            for fn in fns:
                if fn.endswith('.py'):
                    targets.append(os.path.join(dp, fn))
    total = 0
    for t in targets:
        for fn, path, ln, name, imp_ln in scan_file(t):
            total += 1
            print('[隐患] %s:%d  函数 %s() 使用 %s，但该名在函数内 %d 行才导入'
                  % (path, ln, fn, name, imp_ln))
    if total:
        print('\n共 %d 处局部导入遮蔽隐患 —— 运行时会抛 UnboundLocalError，'
              '被 except 吞掉后表现为"某功能静默不生效"' % total)
        return 1
    print('局部导入遮蔽检查通过（0 处隐患）')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
