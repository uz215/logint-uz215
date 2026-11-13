# -*- coding: utf-8 -*-
"""静态检查：函数里引用了不存在的全局名（开发期防呆工具）。

背景
----
``logsys`` 里多处用 ``except Exception: pass`` 做降级 —— 符合本包"任何单步
失败都降级而不抛错"的约定。但它也会**掩盖编程错误**：曾出现
``def snapshot_products(product_root)`` 却在函数体里写 ``products_root``，
NameError 被 except 吞掉，函数静默返回空字典，归集功能整条失效却毫无征兆。

本模块用标准库 ``symtable`` 静态找出这类"引用了不存在的全局名"。

运行
----
    python -m logsys.lint_undef                      # 扫 logsys/ 与 logInt.py
    python -m logsys.lint_undef logsys               # 只扫某个目录

退出码 0 = 无告警，1 = 有告警。
"""
from __future__ import annotations

import builtins
import io
import os
import symtable
import sys

BUILTINS = set(dir(builtins)) | {'__file__', '__name__', '__doc__', '__package__',
                               '__spec__', '__loader__', '__builtins__'}


def module_names(st) -> set:
    """模块顶层定义的名字（函数、类、变量、导入）。"""
    return {s.get_name() for s in st.get_symbols()}


def walk(t, mod_names: set, path: str, out: list, stack: list):
    for sym in t.get_symbols():
        n = sym.get_name()
        # global 且本作用域未赋值 → 引用的是模块级/内置名
        if sym.is_global() and not sym.is_assigned() and not sym.is_parameter():
            if n not in mod_names and n not in BUILTINS:
                out.append((path, ' > '.join(stack), n))
    for child in t.get_children():
        walk(child, mod_names, path, out, stack + [t.get_name()])


def check_file(path: str) -> list:
    try:
        # 用 utf-8-sig 读，剥掉 BOM（部分历史文件带 BOM，symtable 不接受）
        src = io.open(path, encoding='utf-8-sig').read()
        st = symtable.symtable(src, path, 'exec')
    except SyntaxError as e:
        return [(path, '<syntax>', 'SyntaxError: %s' % e)]
    out = []
    walk(st, module_names(st), path, out, [os.path.basename(path)])
    return out


def main() -> int:
    targets = []
    for arg in sys.argv[1:] or ['logsys', 'logInt.py']:
        if os.path.isdir(arg):
            for f in sorted(os.listdir(arg)):
                if f.endswith('.py'):
                    targets.append(os.path.join(arg, f))
        elif os.path.isfile(arg):
            targets.append(arg)
    total = 0
    for p in targets:
        for path, scope, name in check_file(p):
            print('[未定义全局名] %s  [%s]  %s' % (path, scope, name))
            total += 1
    print('-' * 60)
    print('扫描 %d 个文件，发现 %d 处引用了不存在的全局名' % (len(targets), total))
    return 0 if total == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
