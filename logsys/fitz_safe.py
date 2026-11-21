# -*- coding: utf-8 -*-
"""PyMuPDF(fitz) 安全导入——规避 onnxruntime C 扩展与 Qt/Matplotlib 的 DLL 冲突。

背景（R84）：
    本机 pymupdf 新版在 ``import fitz`` 时会执行
    ``pymupdf.layout.activate()``，无条件加载 onnxruntime 的原生扩展
    ``onnxruntime.capi._pybind_state``。若此时 Qt5 / matplotlib 的 DLL 已先
    驻留进程，onnxruntime 加载触发 access violation（Python 直接 exit 139，
    faulthandler 栈停在 ``_pybind_state.py:32`` 的 create_module）。

    本项目只用 fitz 做 ``open / get_text / get_pixmap``（文本与栅格提取），
    从不用 pymupdf 的 ONNX 版式分析（layout）。因此只要在**任何 Qt /
    matplotlib 导入之前**先 ``import fitz``，让 onnxruntime 在干净进程态加载，
    其后所有 ``import fitz`` 都命中 sys.modules 缓存，不再触发冲突。

用法：
    在进程最早入口（主程序顶部 / GUI 基础层 / 独立 CLI）调用一次::

        from logsys.fitz_safe import preload
        preload()

    之后各模块照常 ``import fitz`` 即可，无需改动每处导入点。

幂等：多次调用无副作用；onnxruntime 不可用时降级为普通 import（仅警告），
不影响 fitz 基本功能。
"""
from __future__ import annotations

_DONE = False


def preload() -> None:
    """在任何 Qt/Matplotlib 之前预导入 fitz，锁定 onnxruntime 的加载时机。"""
    global _DONE
    if _DONE:
        return
    _DONE = True
    try:
        import fitz  # noqa: F401,F811  —— 故意早导入，副作用即目的
    except Exception as exc:  # onnxruntime 缺失/损坏时不应阻断主流程
        import sys
        print('[fitz_safe] 预导入 PyMuPDF 失败（后续 PDF 功能可能不可用）: %s' % exc,
              file=sys.stderr)
