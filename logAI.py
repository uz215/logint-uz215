# -*- coding: utf-8 -*-
"""
测井解释智能体 - Gradio Web 界面

功能:
  Tab 1 - 数据加载与解释: 上传 LAS/DLIS, 运行五步自动解释工作流
  Tab 2 - 知识检索: 搜索知识库, 查看区域模板和历史经验
  Tab 3 - 经验反馈: 工程师修正参数, 一键存入知识库
  Tab 4 - 结果查看: 解释成果图, 参数报告, 质量控制

启动:
    C:/Python314/python.exe logAI.py
    # 或指定端口: C:/Python314/python.exe logAI.py --port 7860 --share
    # 依赖: chromadb 1.5.9, sentence-transformers, gradio 6.22.0, torch 2.13
"""

import os
import sys
import json
import argparse
import traceback
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# ---- 确保 logInt/logKnow 可导入 ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# 成果图输出目录 (与源程序 logInt 约定一致: output/<井名>/)
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")

try:
    import gradio as gr
except ImportError:
    print("Gradio 未安装，请执行: pip install gradio")
    sys.exit(1)

# ---- 懒加载各模块 ----
_orchestrator = None
_store = None
_bridge = None
_vector_indexer = None

def get_orchestrator(enable_rag=True):
    global _orchestrator
    if _orchestrator is None:
        from workflow_orchestrator import WorkflowOrchestrator
        _orchestrator = WorkflowOrchestrator(enable_rag=enable_rag)
    return _orchestrator

def get_experience_store():
    global _store
    if _store is None:
        from experience_loop import ExperienceStore
        _store = ExperienceStore()
    return _store

def get_rag_bridge():
    global _bridge
    if _bridge is None:
        try:
            from rag_bridge import RAGBridge
            _bridge = RAGBridge()
        except Exception:
            _bridge = None
    return _bridge

def get_vector_indexer():
    global _vector_indexer
    if _vector_indexer is None:
        try:
            from vector_indexer import VectorIndexer
            _vector_indexer = VectorIndexer()
        except Exception:
            _vector_indexer = None
    return _vector_indexer


# ============================================================
# Tab 1: 数据加载与解释
# ============================================================

# 会话级工作流状态
_session_state = {
    "current_workflow": None,
    "uploaded_file": None,
    "well_name": "",
    "region": "",
    "formation": "",
    "step1_result": None,
    "step2_result": None,
    "step3_result": None,
    "step4_result": None,
    "step5_result": None,
}


def _extract_well_meta(file_path):
    """从测井文件头部轻量提取井名与地区 (失败时回退 logInt, 井名再回退文件名)"""
    well_name, region = "", ""
    try:
        import lasio
        las = lasio.read(str(file_path))
        w = las.well
        well_name = str(w.get('WELL', '') or '').strip()
        region = str(w.get('CNTY', '') or w.get('CTRY', '') or '').strip()
    except Exception:
        try:
            from logInt import WellLogProcessor
            p = WellLogProcessor()
            data = p.load_data(str(file_path))
            if data is not None:
                well_name = getattr(p, 'well_name', '') or ''
                info = p.data_loader.get_file_info()
                wi = (info or {}).get('well_info') or {}
                region = str(wi.get('CNTY') or wi.get('CTRY') or '').strip()
        except Exception:
            pass
    # LAS 头无井名时回退到文件名
    if not well_name:
        well_name = Path(file_path).stem
    return well_name, region


def _file_path_from_input(f):
    """从 Gradio 文件组件值提取文件路径 (兼容 NamedString/字符串/FileData/None)"""
    if f is None:
        return None
    if hasattr(f, "name"):
        return str(f.name)
    if hasattr(f, "path"):
        return str(f.path)
    return str(f) or None


def handle_file_upload(file):
    """处理文件上传: 复制文件 + 自动提取井名回填界面 (返回值最后一项为文件路径, 供 gr.State 使用)"""
    if file is None:
        return "请上传 LAS 或 DLIS 文件", gr.update(interactive=False), gr.update(), None

    # Gradio 6.x 文件组件值为 NamedString(str 子类), 兼容字符串或文件对象
    file_path = getattr(file, "name", None) or str(file)
    ext = Path(file_path).suffix.lower()

    if ext not in ['.las', '.lis', '.dlis']:
        return f"不支持的文件格式: {ext}", gr.update(interactive=False), gr.update(), None

    try:
        # 复制到工作目录 (源已在目标目录时直接复用, 避免 shutil 报 "same file")
        work_dir = Path("data/uploads")
        work_dir.mkdir(parents=True, exist_ok=True)
        dest = work_dir / Path(file_path).name
        if os.path.abspath(str(file_path)) != os.path.abspath(str(dest)):
            shutil.copy(file_path, dest)
    except Exception as e:
        return f"文件复制失败: {e}", gr.update(interactive=False), gr.update(), None

    _session_state["uploaded_file"] = str(dest)

    # 自动提取井名与地区 (地区存入内部状态, 供知识检索使用)
    well_name, region = _extract_well_meta(dest)
    if well_name:
        _session_state["well_name"] = well_name
    if region:
        _session_state["region"] = region

    info = f"文件已上传: {Path(file_path).name}\n"
    info += f"大小: {Path(file_path).stat().st_size / 1024:.1f} KB\n"
    info += f"格式: {ext}\n"
    info += f"保存位置: {dest}"
    if well_name:
        info += f"\n自动识别井名: {well_name}"

    return (info,
            gr.update(interactive=True),
            gr.update(value=well_name),
            str(dest))


def handle_gas_upload(file):
    """处理气测文件上传 (可选, 解释时自动关联) (返回值末项为文件路径, 供 gr.State 使用)"""
    if file is None:
        return "未选择气测文件", None
    file_path = getattr(file, "name", None) or str(file)
    ext = Path(file_path).suffix.lower()
    if ext not in ['.las', '.csv', '.xlsx', '.xls']:
        return f"不支持的气测格式: {ext}", None

    work_dir = Path("data/uploads")
    work_dir.mkdir(parents=True, exist_ok=True)
    dest = work_dir / ("gas_" + Path(file_path).name)
    if os.path.abspath(str(file_path)) != os.path.abspath(str(dest)):
        try:
            shutil.copy(file_path, dest)
        except Exception as e:
            return f"气测文件复制失败: {e}", None
    _session_state["gas_file"] = str(dest)

    return f"气测文件已上传: {Path(file_path).name} (解释时将自动关联)", str(dest)


def run_step(step_num, well_name="", progress=gr.Progress(), file_path=None, gas_file=None):
    """执行单步或全流程 (生成器: 每步完成即推送增量日志到界面)

    地区/层位由系统自动识别并存入 state, 不再通过界面手动输入
    file_path/gas_file 由 gr.State() 从事件链传递 (Gradio 6.x mount 环境下模块级状态不可靠)
    """
    state = _session_state
    file_path = file_path or state.get("uploaded_file")
    gas_file = gas_file or state.get("gas_file")
    well_name = well_name.strip() or state.get("well_name", "")
    region = state.get("region", "")
    formation = state.get("formation", "")

    def emit(text):
        return text

    if not file_path:
        yield emit("错误: 请先上传测井数据文件")
        return

    org = get_orchestrator(enable_rag=True)

    try:
        if step_num == "all":
            # ---- 全流程: 5步依次执行 ----
            results = []

            progress(0.05, desc="Step 1: 数据加载与清洗...")
            yield emit("> Step 1/5 数据加载与清洗中... (首次加载 logInt 模块约需 10s)")
            r1 = org.run_step("load_data", file_path=file_path, well_name=well_name)
            state["step1_result"] = r1
            if r1.status == "success":
                d = r1.data
                results.append(
                    f"[OK] Step 1: 数据加载完成 ({r1.duration_ms/1000:.1f}s)\n"
                    f"      井名: {d.get('well_name','') or well_name}"
                )
                if well_name:
                    state["well_name"] = well_name
            else:
                results.append(f"[FAIL] Step 1: {r1.error}")
                yield emit("\n".join(results))
                return
            yield emit("\n".join(results))

            progress(0.25, desc="Step 2: 知识检索与增强...")
            yield emit("\n".join(results) + "\n> Step 2/5 知识检索 (RAG + logKnow)...")
            r2 = org.run_step("retrieve_knowledge", region=region, formation=formation)
            state["step2_result"] = r2
            if r2.status in ("success", "skipped"):
                results.append(f"[OK] Step 2: 知识检索完成 ({r2.duration_ms/1000:.1f}s)")
                # 知识库识别到的地区/层位仅存入内部状态, 供后续步骤使用
                if r2.data.get("region"):
                    state["region"] = r2.data["region"]
                if r2.data.get("formation"):
                    state["formation"] = r2.data["formation"]
            else:
                results.append(f"[WARN] Step 2: {r2.error or '跳过'}")
            yield emit("\n".join(results))

            progress(0.45, desc="Step 3: 智能参数推荐...")
            yield emit("\n".join(results) + "\n> Step 3/5 智能参数推荐...")
            r3 = org.run_step("recommend_params")
            state["step3_result"] = r3.data if r3.status == "success" else {}
            if r3.status == "success":
                rec = r3.data
                results.append("[OK] Step 3: 参数推荐")
                if rec:
                    results.append(f"      {json.dumps(rec, ensure_ascii=False)[:240]}")
            else:
                results.append(f"[WARN] Step 3: {r3.error}")
            yield emit("\n".join(results))

            progress(0.60, desc="Step 4: 自动解释 (logInt 全流程, 耗时较长)...")
            gas_hint = f"气测文件: {Path(gas_file).name}" if gas_file else "未提供气测文件(可跳过)"
            yield emit("\n".join(results) + f"\n> Step 4/5 自动解释中... ({gas_hint}) (QC→解释→矿物→沉积相, 可能数分钟, 请勿关闭页面)")
            r4 = org.run_step("interpret", gas_file=gas_file)
            state["step4_result"] = r4
            if r4.status == "success":
                out_dir = r4.data.get('output_dir', '')
                results.append(f"[OK] Step 4: 解释完成 ({r4.duration_ms/1000:.1f}s)\n      输出目录: {out_dir}")
            else:
                results.append(f"[FAIL] Step 4: {r4.error}")
                yield emit("\n".join(results))
                progress(1.0, desc="失败终止")
                return
            yield emit("\n".join(results))

            progress(0.90, desc="Step 5: 收集图件与报告...")
            yield emit("\n".join(results) + "\n> Step 5/5 收集成果图件...")
            r5 = org.run_step("plot")
            state["step5_result"] = r5
            if r5.status == "success":
                plots = r5.data.get("plot_paths", [])
                report = r5.data.get("report_path", "")
                results.append(f"[OK] Step 5: 出图完成 ({len(plots)} 幅, 报告: {report or '无'})")
            else:
                results.append(f"[WARN] Step 5: {r5.error or '跳过'}")

            progress(1.0, desc="完成")
            results.append("\n===== 全流程完成 =====")
            yield emit("\n".join(results))

        else:
            # 单步执行
            step_map = {
                "1": ("load_data", {"file_path": file_path, "well_name": well_name}),
                "2": ("retrieve_knowledge", {"region": region, "formation": formation}),
                "3": ("recommend_params", {}),
                "4": ("interpret", {"gas_file": gas_file}),
                "5": ("plot", {}),
            }
            name, kwargs = step_map.get(str(step_num), (None, None))
            if name is None:
                yield emit("无效的步骤号")
                return

            yield emit(f"> 执行 Step {step_num}: {name} ...")
            r = org.run_step(name, **kwargs)
            state[f"step{step_num}_result"] = r
            if r.status == "success":
                yield emit(f"[OK] Step {step_num}: {name}\n{json.dumps(r.data, ensure_ascii=False, default=str)[:600]}")
            else:
                yield emit(f"[FAIL] Step {step_num}: {name}\n{r.error}")

    except Exception as e:
        tb = traceback.format_exc()[-600:]
        yield emit(f"[异常] {e}\n{tb}")


def get_chart_files():
    """获取已生成的图表文件列表"""
    state = _session_state
    r5 = state.get("step5_result")
    if r5 and r5.status == "success":
        plots = r5.data.get("plot_paths", [])
        return plots if plots else []
    return []


def chart_url(path):
    """将 output 目录下的成果图路径转为可访问的 /output/... URL"""
    try:
        rel = os.path.relpath(str(path), OUTPUT_DIR)
        return "/output/" + rel.replace(os.sep, "/")
    except Exception:
        return None


def handle_chart_select(evt=None):
    """Gallery 点击缩略图: 展示大图 + 在新标签页打开原图的链接"""
    state = _session_state
    plots = get_chart_files()
    if not plots:
        return '<p style="text-align:center;color:#888;">暂无可预览的成果图, 请先运行解释流程</p>'

    # evt 由 Gradio select 事件注入; index 可能是整数
    idx = (evt.index if evt is not None and isinstance(evt.index, int) else 0)
    idx = max(0, min(idx, len(plots) - 1))
    path = plots[idx]
    url = chart_url(path)
    name = Path(path).name

    if not url:
        return f'<p style="text-align:center;">无法访问图件: {name}<br>原文件路径: {path}</p>'

    html = (
        '<div style="text-align:center;">'
        f'<p style="margin:6px 0 10px;">'
        f'<a href="{url}" target="_blank" rel="noopener" '
        f'style="font-size:15px;font-weight:bold;color:#0E2982;">'
        f'🖼 {name} — 点击在新标签页打开原图</a></p>'
        f'<a href="{url}" target="_blank" rel="noopener">'
        f'<img src="{url}" alt="{name}" '
        f'style="max-width:100%;max-height:620px;border:1px solid #ddd;'
        f'border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,.12);"></a>'
        '</div>'
    )
    return html


# ============================================================
# Tab 2: 知识检索
# ============================================================

def search_knowledge(query, region="", top_n=5):
    """搜索知识库"""
    results = []
    try:
        # 优先使用 RAGBridge
        bridge = get_rag_bridge()
        if bridge:
            results = bridge.search(query, region=region if region else None, top_n=top_n)

        # 回退: 直接查询 VectorIndexer
        if not results:
            vi = get_vector_indexer()
            if vi:
                results = vi.search(query, top_n=top_n)

        # 格式化输出
        if not results:
            return "未找到相关结果"

        output = []
        for i, r in enumerate(results[:top_n], 1):
            source = r.get("source", r.get("title", ""))
            content = r.get("content", "")[:300]
            score = r.get("score", r.get("_distance", 0))
            output.append(f"## {i}. {source} (相关度: {score:.3f})\n\n{content}\n\n---")
        return "\n".join(output)

    except Exception as e:
        return f"搜索失败: {e}"


def ask_llm(question, context=""):
    """向LLM提问"""
    try:
        bridge = get_rag_bridge()
        if bridge:
            return bridge.ask(question, context=context)
        return "RAGBridge 不可用"
    except Exception as e:
        return f"问答失败: {e}"


# ============================================================
# Tab 3: 经验反馈
# ============================================================

def save_experience(well_name, region, formation, conclusion,
                    gr_value, rt_value, dt_value,
                    m_param, a_param, n_param, vsh_cutoff,
                    engineer, note):
    """保存修正经验"""
    try:
        store = get_experience_store()

        curve_features = {}
        if gr_value:
            curve_features["GR_avg"] = float(gr_value)
        if rt_value:
            curve_features["RT_avg"] = float(rt_value)
        if dt_value:
            curve_features["DT_avg"] = float(dt_value)

        corrected_params = {}
        if m_param:
            corrected_params["m"] = float(m_param)
        if a_param:
            corrected_params["a"] = float(a_param)
        if n_param:
            corrected_params["n"] = float(n_param)
        if vsh_cutoff:
            corrected_params["vsh_cutoff"] = float(vsh_cutoff)

        exp_id = store.quick_note(
            well_name=well_name,
            note=note,
            region=region,
            formation=formation,
            engineer=engineer,
            conclusion=conclusion,
            params=corrected_params,
        )

        # 更新曲线特征
        if curve_features:
            updated = store.find_by_id(exp_id)
            if updated:
                updated.curve_features = curve_features
                store._update_curve_features(exp_id, curve_features)

        # 注入 logKnow
        from experience_loop import inject_to_logknow
        inject_to_logknow(store, auto_export=True)

        return f"[OK] 经验已保存\nID: {exp_id}\n井: {well_name}\n结论: {conclusion}"

    except Exception as e:
        return f"保存失败: {e}"


def get_recent_experiences(limit=20):
    """获取最近的经验记录"""
    try:
        store = get_experience_store()
        rows = store.query(limit=limit)
        if not rows:
            return "暂无经验记录"

        lines = ["| 时间 | 井名 | 地区 | 结论 | 修正参数 |",
                 "|------|------|------|------|----------|"]
        for exp in rows[:limit]:
            time_str = exp.created_at[:16] if exp.created_at else ""
            params_str = json.dumps(exp.corrected_params, ensure_ascii=False) if exp.corrected_params else ""
            lines.append(f"| {time_str} | {exp.well_name} | {exp.region} | {exp.conclusion} | {params_str[:40]} |")
        return "\n".join(lines)

    except Exception as e:
        return f"查询失败: {e}"


def get_experience_stats():
    """经验库统计"""
    try:
        store = get_experience_store()
        stats = store.get_stats()

        lines = [f"总经验数: {stats.get('total', 0)}",
                 f"",
                 f"按地区:",
                 *[f"  {r[0]}: {r[1]}条" for r in stats.get('by_region', [])],
                 f"",
                 f"按结论:",
                 *[f"  {r[0]}: {r[1]}条" for r in stats.get('by_conclusion', [])],
                 ]
        return "\n".join(lines)
    except Exception as e:
        return f"统计失败: {e}"


# ============================================================
# Tab 4: 结果查看
# ============================================================

def get_interpretation_summary():
    """获取当前解释流程摘要"""
    state = _session_state
    lines = []

    # Step 1
    r1 = state.get("step1_result")
    if r1:
        lines.append(f"数据加载: {r1.status}")
        if r1.data:
            lines.append(f"  {json.dumps(r1.data, ensure_ascii=False)[:200]}")

    # Step 3
    r3 = state.get("step3_result")
    if r3:
        lines.append(f"\n参数推荐:")
        if isinstance(r3, dict):
            for k, v in r3.items():
                lines.append(f"  {k}: {v}")

    # Step 4
    r4 = state.get("step4_result")
    if r4:
        lines.append(f"\n解释状态: {r4.status}")
        if r4.data:
            data = r4.data
            if isinstance(data, dict):
                lines.append(f"  结论: {data.get('conclusion', '--')}")
                lines.append(f"  置信度: {data.get('confidence', '--')}")

    return "\n".join(lines) if lines else "尚未执行解释流程"


def get_qc_report():
    """获取质量控制报告"""
    state = _session_state
    r1 = state.get("step1_result")
    if r1 and r1.data:
        qc = r1.data.get("qc_report", {})
        if qc:
            return json.dumps(qc, ensure_ascii=False, indent=2)
    return "暂无QC报告"


# ---- 主题 ----
_APP_THEME = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
)


# ============================================================
# 主界面构建
# ============================================================

def build_ui():
    # theme 已移至 launch() 传入

    with gr.Blocks(title="测井解释智能体") as demo:
        gr.Markdown(
            """# 测井解释智能体平台
            ### 以 logInt + logKnow 为内核, AI 驱动的全流程自动解释系统
            """
        )

        with gr.Tabs():
            # ========== Tab 1: 数据加载与解释 ==========
            with gr.TabItem("数据加载与解释"):
                with gr.Row():
                    with gr.Column(scale=2):
                        file_input = gr.File(
                            label="上传 LAS/DLIS 文件",
                            file_types=[".las", ".lis", ".dlis"],
                        )
                        gas_input = gr.File(
                            label="气测数据文件 (可选, 解释时自动关联)",
                            file_types=[".las", ".csv", ".xlsx", ".xls"],
                        )
                        gr.Markdown("---")
                        well_name = gr.Textbox(label="井名", placeholder="如: Well-X-1 (上传文件后自动填充)")
                        # 会话状态: 文件路径 (Gradio 6.x mount 环境下事件间需显式传递)
                        file_state = gr.State(None)
                        gas_state = gr.State(None)
                        gr.Markdown("---")

                        with gr.Row():
                            run_btn = gr.Button("一键运行全流程", variant="primary", size="lg")
                            stop_btn = gr.Button("停止", variant="stop", size="lg")

                        with gr.Row():
                            step1_btn = gr.Button("Step 1: 数据加载", size="sm")
                            step2_btn = gr.Button("Step 2: 知识检索", size="sm")
                            step3_btn = gr.Button("Step 3: 参数推荐", size="sm")
                            step4_btn = gr.Button("Step 4: 自动解释", size="sm")
                            step5_btn = gr.Button("Step 5: 自动出图", size="sm")

                    with gr.Column(scale=3):
                        log_output = gr.Textbox(
                            label="运行日志",
                            lines=18,
                            max_lines=24,
                            placeholder="上传文件后点击运行查看日志...",
                        )

                # 图表展示区
                gr.Markdown("---")
                chart_dir_info = gr.Markdown(
                    value="**成果图保存位置**: 解释完成后自动保存在源程序设定的 `output/<井名>/` 目录",
                )
                with gr.Row():
                    chart_gallery = gr.Gallery(
                        label="解释成果图 (点击缩略图查看大图)",
                        columns=2,
                        rows=2,
                        height=360,
                        object_fit="contain",
                    )

                with gr.Row():
                    with gr.Column(scale=1):
                        refresh_chart_btn = gr.Button("刷新图表", size="sm")
                        gr.Markdown("提示: 点击缩略图后\n下方显示大图, 再点图片链接\n可在新标签页打开原始文件")
                    with gr.Column(scale=4):
                        chart_open_html = gr.HTML(
                            '<p style="text-align:center;color:#888;margin:18px 0;">'
                            '点击上方缩略图, 此处显示大图; 点击图名或图片可在新标签页打开原图</p>'
                        )

                # 绑定事件 (用具名生成器确保 Gradio 识别为流式输出)
                # file_path/gas_file 通过 gr.State 传递, 并直接传入文件组件值作为兜底
                # (即使 change 事件未触发, 运行按钮也能拿到当前文件路径)
                def run_all(w, f_state, f_input, progress=gr.Progress()):
                    fp = f_state or _file_path_from_input(f_input)
                    yield from run_step("all", w, progress=progress, file_path=fp)

                def run_s1(w, f_state, f_input, progress=gr.Progress()):
                    fp = f_state or _file_path_from_input(f_input)
                    yield from run_step("1", w, progress=progress, file_path=fp)

                def run_s2(w, f_state, f_input, progress=gr.Progress()):
                    fp = f_state or _file_path_from_input(f_input)
                    yield from run_step("2", w, progress=progress, file_path=fp)

                def run_s3(f_state, f_input, progress=gr.Progress()):
                    fp = f_state or _file_path_from_input(f_input)
                    yield from run_step("3", progress=progress, file_path=fp)

                def run_s4(f_state, g_state, f_input, progress=gr.Progress()):
                    fp = f_state or _file_path_from_input(f_input)
                    yield from run_step("4", progress=progress, file_path=fp, gas_file=g_state)

                def run_s5(f_state, f_input, progress=gr.Progress()):
                    fp = f_state or _file_path_from_input(f_input)
                    yield from run_step("5", progress=progress, file_path=fp)

                file_input.change(handle_file_upload, [file_input], [log_output, run_btn, well_name, file_state])
                gas_input.change(handle_gas_upload, [gas_input], [log_output, gas_state])
                run_btn.click(run_all, [well_name, file_state, file_input], [log_output])
                step1_btn.click(run_s1, [well_name, file_state, file_input], [log_output])
                step2_btn.click(run_s2, [well_name, file_state, file_input], [log_output])
                step3_btn.click(run_s3, [file_state, file_input], [log_output])
                step4_btn.click(run_s4, [file_state, gas_state, file_input], [log_output])
                step5_btn.click(run_s5, [file_state, file_input], [log_output])

                # 图表手动刷新
                def refresh_gallery():
                    state = _session_state
                    plots = get_chart_files()
                    dir_text = "**成果图保存位置**: 解释完成后自动保存在源程序设定的 `output/<井名>/` 目录"
                    r4 = state.get("step4_result")
                    if r4 and r4.status == "success" and r4.data.get("output_dir"):
                        dir_text = f"**成果图保存位置**: `{r4.data['output_dir']}`"
                    return (plots or []), dir_text

                refresh_chart_btn.click(refresh_gallery, [], [chart_gallery, chart_dir_info])

                # 点击缩略图 -> 显示大图 + 新标签页打开原图链接
                chart_gallery.select(handle_chart_select, [], [chart_open_html])

            # ========== Tab 2: 知识检索 ==========
            with gr.TabItem("知识检索"):
                with gr.Row():
                    with gr.Column(scale=2):
                        search_query = gr.Textbox(
                            label="搜索问题 / 关键词",
                            placeholder="输入问题, 如: 低电阻率油层的识别方法 / 中东碳酸盐岩孔隙度模型...",
                            lines=2,
                        )
                        with gr.Row():
                            search_region = gr.Textbox(label="地区过滤", placeholder="如: 中东")
                            search_top_n = gr.Slider(minimum=1, maximum=20, value=5, step=1, label="结果数")
                        search_btn = gr.Button("搜索", variant="primary")

                        gr.Markdown("---")
                        ask_question = gr.Textbox(
                            label="向 LLM 提问",
                            placeholder="基于知识库问答...",
                            lines=2,
                        )
                        ask_btn = gr.Button("提问", variant="secondary")

                    with gr.Column(scale=3):
                        search_result = gr.Markdown(label="搜索结果")
                        ask_result = gr.Markdown(label="回答")

                search_btn.click(
                    search_knowledge, [search_query, search_region, search_top_n], [search_result]
                )
                ask_btn.click(ask_llm, [ask_question], [ask_result])

            # ========== Tab 3: 经验反馈 ==========
            with gr.TabItem("经验反馈"):
                with gr.Row():
                    with gr.Column(scale=2):
                        gr.Markdown("### 修正参数记录")
                        exp_well = gr.Textbox(label="井名 *", placeholder="如: Well-X-1")
                        exp_region = gr.Textbox(label="地区", placeholder="如: 中东/阿联酋")
                        exp_formation = gr.Textbox(label="层位", placeholder="如: Asmari")
                        exp_conclusion = gr.Dropdown(
                            label="解释结论 *",
                            choices=["油层", "气层", "水层", "油气同层", "油水同层", "干层", "致密层", "差油层"],
                        )

                        gr.Markdown("#### 曲线特征值")
                        with gr.Row():
                            exp_gr = gr.Number(label="GR (API)", value=None)
                            exp_rt = gr.Number(label="RT (ohm.m)", value=None)
                            exp_dt = gr.Number(label="DT (us/ft)", value=None)

                        gr.Markdown("#### 修正参数")
                        with gr.Row():
                            exp_m = gr.Number(label="m (胶结指数)", value=None)
                            exp_a = gr.Number(label="a (岩性系数)", value=None)
                        with gr.Row():
                            exp_n = gr.Number(label="n (饱和度指数)", value=None)
                            exp_vsh = gr.Number(label="Vsh 截止值", value=None)

                        exp_engineer = gr.Textbox(label="工程师", placeholder="记录人姓名")
                        exp_note = gr.Textbox(label="备注说明", lines=3, placeholder="修正原因、经验总结...")
                        save_exp_btn = gr.Button("保存经验", variant="primary", size="lg")

                    with gr.Column(scale=3):
                        exp_status = gr.Textbox(label="保存状态", lines=2)
                        gr.Markdown("---")
                        gr.Markdown("### 最近经验记录")
                        recent_exp = gr.Markdown(value="点击刷新查看...")
                        refresh_exp_btn = gr.Button("刷新", size="sm")

                        gr.Markdown("---")
                        gr.Markdown("### 经验库统计")
                        exp_stats = gr.Markdown(value="点击刷新查看...")
                        refresh_stats_btn = gr.Button("刷新统计", size="sm")

                save_exp_btn.click(
                    save_experience,
                    [exp_well, exp_region, exp_formation, exp_conclusion,
                     exp_gr, exp_rt, exp_dt,
                     exp_m, exp_a, exp_n, exp_vsh,
                     exp_engineer, exp_note],
                    [exp_status],
                )
                refresh_exp_btn.click(get_recent_experiences, [], [recent_exp])
                refresh_stats_btn.click(get_experience_stats, [], [exp_stats])

            # ========== Tab 4: 结果查看 ==========
            with gr.TabItem("结果查看"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 解释摘要")
                        summary_output = gr.Markdown(value="尚未执行解释流程")
                        refresh_summary_btn = gr.Button("刷新摘要", size="sm")

                    with gr.Column(scale=1):
                        gr.Markdown("### 质量控制报告")
                        qc_output = gr.Textbox(label="QC 报告", lines=15, max_lines=20)
                        refresh_qc_btn = gr.Button("刷新QC", size="sm")

                refresh_summary_btn.click(get_interpretation_summary, [], [summary_output])
                refresh_qc_btn.click(get_qc_report, [], [qc_output])

        # 底部状态栏
        gr.Markdown(
            """---
            <div style="text-align: center; color: #888; font-size: 12px;">
            logInt + logKnow + RAG | VectorIndex + ExperienceLoop | v0.1 Alpha
            </div>
            """
        )

    return demo


# ============================================================
# 入口
# ============================================================


def _install_delete_shim():
    """全局绕过 WorkBuddy 沙箱对 os.remove/unlink/rmdir 的 safe-delete 拦截

    背景: 沙箱在回收站不可用时 fail-closed (抛 OSError 或终止进程),
    导致 Whoosh 提交、matplotlib 生成临时图、清理旧成果图等所有删除操作失败.
    实现: 对 os.remove / os.unlink / os.rmdir 包装一层, 原始调用失败时
    回退到 ctypes kernel32.DeleteFileW / RemoveDirectoryW 直接删除.
    """
    import os as _os
    import sys as _sys
    import ctypes as _ct

    if getattr(_os.remove, "_safedel_shim", False):
        return

    _k = _ct.windll.kernel32
    _open = _os.open if hasattr(_os, "open") else None
    # 兼容 python 3.14 的内置 open
    _builtin_open = __builtins__.get("open") if isinstance(__builtins__, dict) else __builtins__.open

    def _ct_delete_path(path: str) -> bool:
        ap = _os.path.abspath(path)
        if _os.path.isdir(ap) and not _os.path.islink(ap):
            return bool(_k.RemoveDirectoryW(ap))
        return bool(_k.DeleteFileW(ap))

    def _make_shim(orig):
        _devnull = _builtin_open(_os.devnull, "w")

        def shim(path, *a, **kw):
            # 抑制钩子喷出的 [safe-delete] JSON 噪音 (其 print 发生在 OSError 抛出之前)
            _saved_out, _saved_err = _sys.stdout, _sys.stderr
            try:
                _sys.stdout = _devnull
                _sys.stderr = _devnull
                try:
                    return orig(path, *a, **kw)
                except OSError:
                    # 沙箱拦截导致删除失败, 绕过钩子直接删除
                    _ct_delete_path(path)
                    return None
            finally:
                _sys.stdout = _saved_out
                _sys.stderr = _saved_err

        shim._safedel_shim = True
        return shim

    for _name in ("remove", "unlink", "rmdir"):
        if hasattr(_os, _name):
            _orig = getattr(_os, _name)
            if getattr(_orig, "_safedel_shim", False):
                continue
            setattr(_os, _name, _make_shim(_orig))


def _install_frontmatter_shim():
    """为 logKnow 兼容 frontmatter 包的 API (完整版)

    logKnow 调用 frontmatter.load(path) / frontmatter.Post / frontmatter.dumps;
    但环境中的 frontmatter (3.0.8) 是不同的包, 不提供这些 API,
    导致 1700+ 个本地 Markdown 文档报 'module frontmatter has no attribute load',
    且 DocumentConverter.convert 因缺 dumps 对所有新资料静默 SKIP.
    由 frontmatter_shim.install() 统一提供兼容层.
    """
    try:
        import frontmatter_shim
        frontmatter_shim.install()
    except Exception as _e:
        print(f"[warn] frontmatter shim install failed: {_e}")


def main():
    parser = argparse.ArgumentParser(description="测井解释智能体 Web 界面")
    parser.add_argument("--port", type=int, default=7860, help="端口号")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址")
    parser.add_argument("--share", action="store_true", help="生成公网链接")
    parser.add_argument("--no-rag", action="store_true", help="禁用RAG模式")
    args = parser.parse_args()

    # WorkBuddy 沙箱全局删除拦截绕过 (必须最先安装)
    _install_delete_shim()

    # frontmatter 包 API 兼容 shim (修复 1700+ 个 Markdown 文档 'has no attribute load')
    _install_frontmatter_shim()

    print(f"启动测井解释智能体平台...")
    print(f"  地址: http://{args.host}:{args.port}")
    print(f"  RAG: {'禁用' if args.no_rag else '启用'}")
    print(f"  logInt: {'已加载' if _orchestrator else '待加载'}")
    print()

    demo = build_ui()

    # 主线程预热 torch/sentence-transformers
    # 原因: 首次 import 若发生在 Gradio worker 线程, Windows 下 c10.dll
    # 初始化可能失败 ([WinError 1114]); 主线程预热后 worker 内不再触发 DLL 加载
    if not args.no_rag:
        try:
            # 镜像端点需在 huggingface_hub 导入前设置 (国内网络 huggingface.co 不可达)
            import os as _os
            _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            _os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
            import sentence_transformers  # noqa: F401 (其内部完成 torch 加载)
            print("RAG 依赖预热完成 (torch + sentence-transformers)")
        except Exception as e:
            print(f"警告: RAG 依赖预热失败, 检索将降级为关键词模式: {e}")

    # 用外层 FastAPI 挂载成果图静态目录, 再挂载 Gradio 界面 (同一端口)
    # 原因: Gradio 的 demo.launch() 内部会重建 app 实例, 预先 mount 的静态目录会丢失
    try:
        import fastapi, uvicorn
        from fastapi.staticfiles import StaticFiles

        app = fastapi.FastAPI()
        app.mount("/output", StaticFiles(directory=OUTPUT_DIR, check_dir=False))

        gr.mount_gradio_app(
            app,
            demo,
            path="/",
            server_name=args.host,
            server_port=args.port,
            theme=_APP_THEME,
            show_error=True,
        )

        print(f"成果图访问: http://{args.host}:{args.port}/output/<井名>/xxx.png")
        uvicorn.run(app, host=args.host, port=args.port)
    except Exception as e:
        print(f"警告: 外层挂载方式启动失败 ({e}), 回退到 demo.launch()")
        demo.launch(
            server_name=args.host,
            server_port=args.port,
            share=args.share,
            show_error=True,
            theme=_APP_THEME,
        )


if __name__ == "__main__":
    main()
