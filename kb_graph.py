#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_graph.py - 可校正知识条目 → 知识库/图谱 同步工具（2026-10-28 R40）。

背景（用户定调，K-SYS-001）：用户口述的标准/要求是知识源，可能片面、
不对、或只适用特定区域——须经井数据验证校正后，沉淀为可版本化、可
修正、可追溯的知识条目，加入知识库并形成图谱。

条目库（正本，git 版本化 = 校正史）:
    knowledge/entries/*.md
条目格式（frontmatter）:
    id / title / type / scope / status(试行|已验证|已修正|已废止)
    version / date / source / supersedes(列表) / relates(列表)
    code_ref / tags
    正文含「校正历史」节（每次修正追加一行，不删除旧记录）

本工具产物:
    knowledge/知识图谱总览.md          条目表 + mermaid 关系图（正本）
    data/materials/知识条目/*.md       入库副本（knowledge_build 扫描目录）
    Whoosh 定向增量                    单文档 add，不经全量构建
                                       （全量构建易被外部静默终止，R38 实测）

校正流程:
    1) 编辑 knowledge/entries/<ID>_*.md：version+1、date、status、
       「校正历史」追加一行（日期/改了什么/为什么/依据哪口井）；
    2) python kb_graph.py   （graph + sync + index 一键完成）
    3) git commit（校正史入版本库）。

用法:
    python kb_graph.py            # 全部（graph + sync + index）
    python kb_graph.py graph      # 只重生成图谱总览
    python kb_graph.py sync       # 只同步入库副本
    python kb_graph.py index      # 只定向入 Whoosh 索引
"""
import io
import os
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ENTRIES_DIR = os.path.join(BASE, "knowledge", "entries")
OVERVIEW = os.path.join(BASE, "knowledge", "知识图谱总览.md")
SYNC_DIR = os.path.join(BASE, "data", "materials", "知识条目")

sys.path.insert(0, BASE)


def _load_entries():
    """读取全部条目 frontmatter + 正文。"""
    import frontmatter
    out = []
    if not os.path.isdir(ENTRIES_DIR):
        return out
    for fn in sorted(os.listdir(ENTRIES_DIR)):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(ENTRIES_DIR, fn)
        try:
            post = frontmatter.load(p)
        except Exception as e:
            print("WARN 条目解析失败 %s: %s" % (fn, e))
            continue
        meta = dict(post.metadata)
        meta["_file"] = fn
        meta["_path"] = p
        meta["_content"] = post.content
        out.append(meta)
    return out


def _fmt_list(v):
    if isinstance(v, list):
        return "、".join(str(x) for x in v) if v else "—"
    return str(v) if v else "—"


def gen_graph(entries):
    """生成 knowledge/知识图谱总览.md（条目表 + mermaid 关系图）。"""
    lines = []
    lines.append("---")
    lines.append("title: 知识图谱总览（可校正知识条目库）")
    lines.append("source: kb_graph.py 自动生成，勿手改；正本=knowledge/entries/")
    lines.append("tags: [知识图谱, 元原则, 条目索引]")
    lines.append("---")
    lines.append("")
    lines.append("# 知识图谱总览")
    lines.append("")
    lines.append("> **元原则（K-SYS-001）**：口述标准=知识源，可能片面/不对/区域性；")
    lines.append("> 经井数据验证校正后沉淀为条目（version 递增、校正历史留痕、status 标注），")
    lines.append("> 形成真正的知识加入知识库并形成本图谱。校正流程见 kb_graph.py 文档头。")
    lines.append("")
    lines.append("## 条目清单")
    lines.append("")
    lines.append("| ID | 标题 | 类型 | 适用范围 | 状态 | 版本 | 日期 | 来源 | 修正自 | 关联 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for e in entries:
        lines.append("| %s | %s | %s | %s | %s | v%s | %s | %s | %s | %s |" % (
            e.get("id", "?"), str(e.get("title", "")).replace("|", "／"),
            e.get("type", ""), e.get("scope", ""), e.get("status", ""),
            e.get("version", "1"), e.get("date", ""),
            str(e.get("source", "")).replace("|", "／")[:40],
            _fmt_list(e.get("supersedes")), _fmt_list(e.get("relates"))))
    lines.append("")
    lines.append("## 关系图")
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart LR")
    _ids = {e.get("id", "") for e in entries}
    for e in entries:
        _eid = e.get("id", "?")
        _ttl = str(e.get("title", ""))[:18].replace('"', "'")
        lines.append('    %s["%s %s"]' % (_eid.replace("-", "_"), _eid, _ttl))
    for e in entries:
        _eid = e.get("id", "?")
        for sup in (e.get("supersedes") or []):
            if sup in _ids:
                lines.append("    %s -->|%s 修正自| %s" % (
                    _eid.replace("-", "_"), _eid, str(sup).replace("-", "_")))
        for rel in (e.get("relates") or []):
            if rel in _ids and rel not in (e.get("supersedes") or []):
                lines.append("    %s -.->|%s 关联| %s" % (
                    _eid.replace("-", "_"), _eid, str(rel).replace("-", "_")))
    lines.append("```")
    lines.append("")
    lines.append("## 状态图例")
    lines.append("")
    lines.append("- **试行**：已落判据，阈值/口径仍可能随新井复核校正")
    lines.append("- **已验证**：双井回归通过且经多井复核无反例")
    lines.append("- **已修正**：曾被修正（当前内容为最新版，旧结论在校正历史）")
    lines.append("- **已废止**：被证伪或被新条目替代（留痕不删除）")
    lines.append("")
    with io.open(OVERVIEW, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print("GRAPH  %s（条目 %d 篇）" % (OVERVIEW, len(entries)))


def sync(entries):
    """条目+总览 复制到 data/materials/知识条目/ 供 knowledge_build 入库。"""
    if not os.path.isdir(SYNC_DIR):
        os.makedirs(SYNC_DIR)
    n = 0
    for e in entries:
        dst = os.path.join(SYNC_DIR, e["_file"])
        shutil.copy2(e["_path"], dst)
        n += 1
    dst = os.path.join(SYNC_DIR, "知识图谱总览.md")
    shutil.copy2(OVERVIEW, dst)
    n += 1
    print("SYNC   %s（%d 个文件）" % (SYNC_DIR, n))


def index(entries):
    """定向 Whoosh 增量：条目+总览逐篇 add_document（规避全量构建被杀）。"""
    import __main__ as _m
    from logKnow import WellLogKnowledgeBase, JiebaTokenizer, MarkdownLoader
    _m.JiebaTokenizer = JiebaTokenizer
    kb = WellLogKnowledgeBase(auto_scan=False)
    try:
        kb.stop_auto_update()
    except Exception:
        pass
    loader = MarkdownLoader(SYNC_DIR)
    files = [e["_file"] for e in entries] + ["知识图谱总览.md"]
    ok = 0
    for fn in files:
        p = os.path.join(SYNC_DIR, fn)
        if not os.path.exists(p):
            continue
        doc = loader._load_file(p)
        if not doc:
            print("WARN   加载失败（跳过）: %s" % fn)
            continue
        # frontmatter date 可能是 datetime.date/str，Whoosh DATETIME 要 datetime
        import datetime as _dt
        _ts = doc.get("timestamp")
        if isinstance(_ts, _dt.datetime):
            pass
        elif isinstance(_ts, _dt.date):
            _ts = _dt.datetime(_ts.year, _ts.month, _ts.day)
        else:
            _ts = _dt.datetime.now()
        kb.indexer.add_document(
            title=doc["title"], content=doc["content"], source=doc["source"],
            category=doc.get("category", "local"), timestamp=_ts,
            content_hash=doc.get("content_hash"), well_name=doc.get("well_name") or "",
            region=doc.get("region") or "", oil_field=doc.get("oil_field") or "",
            structure=doc.get("structure") or "", depth_range=doc.get("depth_range") or "",
            file_type=doc.get("file_type") or "")
        ok += 1
        print("INDEX  %s" % fn)
    ix = kb.indexer.get_index()
    with ix.searcher() as s:
        print("INDEX  完成 %d/%d，索引总数 %d" % (ok, len(files), s.doc_count()))


def main():
    cmds = [a for a in sys.argv[1:] if not a.startswith("-")] or \
        ["graph", "sync", "index"]
    entries = _load_entries()
    if not entries:
        print("无条目（%s）" % ENTRIES_DIR)
        return
    for c in cmds:
        if c == "graph":
            gen_graph(entries)
        elif c == "sync":
            sync(entries)
        elif c == "index":
            index(entries)
        else:
            print("未知命令: %s（可用 graph/sync/index）" % c)


if __name__ == "__main__":
    main()
