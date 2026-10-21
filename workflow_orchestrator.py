# -*- coding: utf-8 -*-
"""
智能体编排器 - 将 logInt + logKnow + RAG 串联为五步自动化工作流

五步流水线:
  [1] 数据加载与清洗    -> DataLoader + DataProcessor
  [2] 知识检索与增强    -> RAGBridge + logKnow
  [3] 智能参数推荐      -> LLM + 历史经验
  [4] 自动解释与出图    -> WellLogProcessor + DataVisualizer
  [5] 人机协同修正      -> experience_loop存储

用法:
    orchestrator = WorkflowOrchestrator()
    orchestrator.run("path/to/well.las")

    # 或分步执行
    orchestrator.run_step("load_data", file_path="well.las")
    orchestrator.run_step("retrieve_knowledge")
    orchestrator.run_step("recommend_params")
    orchestrator.run_step("interpret")
    orchestrator.run_step("plot")
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger("workflow_orchestrator")

# ============================================================
# 数据模型
# ============================================================

@dataclass
class StepResult:
    """单步执行结果"""
    step_name: str
    status: str = "pending"         # pending | running | success | failed | skipped
    start_time: str = ""
    end_time: str = ""
    duration_ms: float = 0
    output: Any = None
    error: str = ""
    warnings: List[str] = field(default_factory=list)
    data: Dict = field(default_factory=dict)


@dataclass
class WorkflowState:
    """工作流全局状态"""
    well_name: str = ""
    file_path: str = ""
    region: str = ""
    formation: str = ""
    profile_type: str = ""

    # 各步骤数据
    raw_data: Any = None                   # Step 1 输出
    qc_report: Dict = field(default_factory=dict)
    interpretation_context: Any = None     # Step 2 输出
    parameter_recommendation: Dict = field(default_factory=dict)  # Step 3 输出
    interpretation_results: Dict = field(default_factory=dict)    # Step 4 输出
    plot_paths: List[str] = field(default_factory=list)
    report_path: str = ""

    # 步骤记录
    steps: List[StepResult] = field(default_factory=list)

    # 元数据
    started_at: str = ""
    current_step: str = ""
    curve_features: Dict = field(default_factory=dict)

    def get_step(self, name: str) -> Optional[StepResult]:
        for s in self.steps:
            if s.step_name == name:
                return s
        return None


# ============================================================
# 工作流编排器
# ============================================================

class WorkflowOrchestrator:
    """测井解释智能体编排器"""

    STEPS = [
        "load_data",
        "retrieve_knowledge",
        "recommend_params",
        "interpret",
        "plot",
    ]

    def __init__(self, src_dir: str = None, output_dir: str = "output",
                 enable_rag: bool = True, enable_vector: bool = True,
                 vector_dir: str = "data/vector_index",
                 log_int_instance=None, rag_bridge=None,
                 enable_experience: bool = True, engineer: str = ""):
        """
        Args:
            src_dir: logInt/logKnow 源码目录
            output_dir: 输出目录
            enable_rag: 是否启用 RAG 知识增强
            enable_vector: 向量检索
            vector_dir: 向量库路径
            log_int_instance: 外部传入的 WellLogProcessor 实例
            rag_bridge: 外部传入的 RAGBridge 实例
            enable_experience: 是否自动沉淀解释经验(默认开启, 解决"经验未形成知识")
            engineer: 操作工程师(记入经验)
        """
        self.src_dir = src_dir or str(Path(__file__).parent)
        self.output_dir = output_dir
        self.enable_rag = enable_rag
        self.enable_vector = enable_vector
        self.vector_dir = vector_dir
        self.enable_experience = enable_experience

        self._log_int = log_int_instance
        self._bridge = rag_bridge
        self._state = None
        self._collector = None
        self._hooks: Dict[str, List[Callable]] = {
            "before_step": [],
            "after_step": [],
            "on_error": [],
        }

        os.makedirs(output_dir, exist_ok=True)

        # ---- 经验闭环: 自动把每次解释(参数+约束决策+结论分布)沉淀入库 ----
        # 原实现只提供了 ExperienceCollector 类但从未绑定, 经验库长期为空,
        # 导致"多次解释结果有差异"无从追溯。此处默认绑定。
        if enable_experience:
            try:
                from experience_loop import ExperienceStore, ExperienceCollector
                self._collector = ExperienceCollector(
                    store=ExperienceStore(), engineer=engineer)
                self._collector.attach_to_orchestrator(self)
            except Exception as e:
                logger.warning(f"经验收集器绑定失败(不影响解释): {e}")
                self._collector = None

    # ---------- 生命周期 ----------

    def run(self, file_path: str, well_name: str = None,
            interactive: bool = False) -> WorkflowState:
        """运行完整五步工作流

        Args:
            file_path: LAS/DLIS 文件路径
            well_name: 井名 (None则从文件提取)
            interactive: 是否交互模式(每步完成后暂停)

        Returns:
            WorkflowState
        """
        self._state = WorkflowState(
            file_path=file_path,
            well_name=well_name or Path(file_path).stem,
            started_at=datetime.now().isoformat()
        )
        state = self._state

        logger.info(f"========== 启动工作流: {state.well_name} ==========")

        for step_name in self.STEPS:
            if interactive:
                input(f"\n[按 Enter 执行 {step_name}]...")

            self.run_step(step_name)

            # 检查是否需要跳过后续步骤
            step_result = state.get_step(step_name)
            if step_result and step_result.status == "failed":
                logger.error(f"步骤 {step_name} 失败，工作流终止")
                break

        logger.info(f"========== 工作流完成: {state.well_name} ==========")
        self._save_workflow_log(state)

        # 经验回写知识库: 导出经验 MD 并注入索引, 下次解释即可检索到
        if self._collector is not None:
            try:
                from experience_loop import inject_to_logknow
                inject_to_logknow(self._collector.store,
                                  kb_or_bridge=self._bridge, auto_export=True)
            except Exception as e:
                logger.debug(f"经验注入知识库跳过: {e}")

        return state

    def run_step(self, step_name: str, **kwargs) -> StepResult:
        """执行单个步骤

        Args:
            step_name: load_data | retrieve_knowledge | recommend_params | interpret | plot
            **kwargs: 传递给步骤函数的额外参数

        Returns:
            StepResult
        """
        if step_name not in self.STEPS:
            return StepResult(step_name=step_name, status="failed",
                            error=f"未知步骤: {step_name}")

        if self._state is None:
            self._state = WorkflowState(current_step=step_name)

        state = self._state
        state.current_step = step_name

        # 前置钩子
        self._fire_hooks("before_step", step_name)

        result = StepResult(
            step_name=step_name,
            status="running",
            start_time=datetime.now().isoformat()
        )

        try:
            # 调用对应的步骤函数
            step_func = getattr(self, f"_step_{step_name}")
            step_func(state, **kwargs)

            result.status = "success"

            # 回填步骤产出供前端读取
            result.data = self._collect_step_data(step_name, state)

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            logger.error(f"[{step_name}] 执行失败: {e}")
            self._fire_hooks("on_error", step_name, error=e)

        result.end_time = datetime.now().isoformat()
        if result.start_time:
            start = datetime.fromisoformat(result.start_time)
            end = datetime.fromisoformat(result.end_time)
            result.duration_ms = (end - start).total_seconds() * 1000

        state.steps.append(result)

        # 后置钩子
        self._fire_hooks("after_step", step_name, result=result)

        status_icon = "OK" if result.status == "success" else "FAIL"
        logger.info(f"  [{status_icon}] {step_name} ({result.duration_ms:.0f}ms)")

        return result

    # ---------- 步骤实现 ----------

    def _step_load_data(self, state: WorkflowState, file_path: str = None,
                        well_name: str = None):
        """Step 1: 数据加载与清洗"""
        if file_path:
            state.file_path = file_path
        if well_name:
            state.well_name = well_name
        if not state.file_path:
            raise ValueError("未提供数据文件路径 (file_path)")

        logger.info(f"[1/5] 数据加载: {state.file_path}")

        # 初始化 logInt
        if self._log_int is None:
            from logInt import WellLogProcessor
            self._log_int = WellLogProcessor()

        processor = self._log_int
        data = processor.load_data(state.file_path)

        # 加载失败校验 (logInt 内部吞异常, load_data 失败返回 None)
        if data is None:
            raise ValueError(f"数据加载失败: {state.file_path} (文件不存在或格式无法解析)")

        state.raw_data = data

        # 井名: logInt 已从 LAS 头或文件名提取
        if getattr(processor, 'well_name', ''):
            state.well_name = processor.well_name

        # 文件元信息 (地区等)
        try:
            info = processor.data_loader.get_file_info()
            if isinstance(info, dict):
                if info.get('well_name') and not state.well_name:
                    state.well_name = info['well_name']
                well_info = info.get('well_info') or info.get('las_info') or {}
                if isinstance(well_info, dict):
                    state.region = well_info.get('CNTY', '') or well_info.get('CTRY', '') or state.region
        except Exception as e:
            logger.debug(f"提取文件元信息失败: {e}")

        # 运行 QC
        try:
            state.qc_report = processor.data_processor.data_quality_check()
        except Exception as e:
            logger.debug(f"QC 检查失败: {e}")

        # 提取曲线特征
        state.curve_features = self._extract_curve_features(state.raw_data)
        state.formation = self._detect_formation(state.curve_features)
        state.profile_type = self._detect_profile_type(state.curve_features)

        logger.info(f"  井名: {state.well_name}, 地区: {state.region or '未知'}")
        logger.info(f"  层位: {state.formation or '待定'}, 剖面: {state.profile_type}")

    def _step_retrieve_knowledge(self, state: WorkflowState, region: str = None,
                                 formation: str = None):
        """Step 2: 知识检索与增强 (RAG)"""
        if region:
            state.region = region
        if formation:
            state.formation = formation

        if not self.enable_rag:
            logger.info("[2/5] RAG 已禁用，跳过知识检索")
            return

        logger.info(f"[2/5] 知识检索: {state.well_name}")

        if self._bridge is None:
            from rag_bridge import RAGBridge
            self._bridge = RAGBridge(
                embedded=True, src_dir=self.src_dir,
                vector_dir=self.vector_dir
            )
            ok = self._bridge.connect(enable_vector=self.enable_vector)
            if not ok:
                # connect 失败: _backend._kb 仍为 None, 后续 retrieve/recommend
                # 会用纯检索/默认参数路径, 不依赖 builtin_knowledge。
                # 这里只打日志, 不抛错, 保持"有就有、没有就没有"的稳定行为。
                logger.warning("[2/5] RAG 知识库连接失败, 仅使用区域表/默认参数")

        bridge = self._bridge

        # 1. 检测地区
        if not state.region and state.file_path:
            detection = bridge._backend.detect_region(state.file_path)
            if detection:
                state.region = detection.get('region_name', detection.get('region', ''))

        # 2. 检索上下文
        ctx = bridge.retrieve_context(
            well_name=state.well_name,
            region=state.region or "",
            formation=state.formation or "",
            profile_type=state.profile_type or "sand_shale",
            curve_features=state.curve_features,
        )
        state.interpretation_context = ctx

        # 3. 搜索相似井
        similar = bridge.search_similar_wells(state.well_name, state.region or "")
        ctx.reference_cases = similar

        # 4. 试油金标准: 相似历史试油层 (油/气/水/干层)
        #    来自结构化试油库 well_test_store.search_similar, 作为流体判别的金标准。
        #    检索结果同时写入 ctx.test_results 与 state.test_gold_standards。
        try:
            from test_gold_standard import search_similar_testzone
            feats = state.curve_features or {}
            gs = search_similar_testzone(
                well_name=state.well_name,
                region=state.region or "",
                formation=state.formation or "",
                phi=feats.get("PHI_avg") or feats.get("phi"),
                rt=feats.get("RT_avg") or feats.get("rt"),
                sw=feats.get("SW_avg") or feats.get("sw"),
                limit=5,
            )
            state.test_gold_standards = gs
            if gs.get("count"):
                ctx.test_results = gs["similar_zones"]
                logger.info(f"  试油金标准: {gs['count']} 条相似试油层")
        except Exception as e:
            logger.debug(f"试油金标准检索跳过: {e}")
            state.test_gold_standards = {"count": 0, "similar_zones": []}

        logger.info(f"  知识片段: {len(ctx.knowledge_snippets)}")
        logger.info(f"  参考案例: {len(ctx.reference_cases or [])}")
        logger.info(f"  试油金标准: {len(ctx.test_results or [])} 条")

    def get_test_gold_standards(self) -> Dict:
        """返回当前工作流的试油金标准 (相似历史试油层), 供上层 LLM/前端读取"""
        if self._state is None:
            return {"count": 0, "similar_zones": []}
        return getattr(self._state, "test_gold_standards",
                       {"count": 0, "similar_zones": []})

    def _step_recommend_params(self, state: WorkflowState):
        """Step 3: 智能参数推荐"""
        logger.info(f"[3/5] 参数推荐")

        if self.enable_rag and self._bridge:
            rec = self._bridge.recommend_parameters(
                well_name=state.well_name,
                region=state.region or "",
                formation=state.formation or "",
                profile_type=state.profile_type or "",
                curve_features=state.curve_features,
            )

            state.parameter_recommendation = rec
            logger.info(f"  Vsh方法={rec.get('vsh_method')}, 截止值={rec.get('vsh_cutoff')}")
            logger.info(f"  a={rec.get('a')}, m={rec.get('m')}, n={rec.get('n')}, Rw={rec.get('rw')}")
            logger.info(f"  骨架: DEN={rec.get('rho_matrix')}, DT={rec.get('dt_matrix')}")
        else:
            # 默认参数
            state.parameter_recommendation = {
                "vsh_method": 3, "vsh_cutoff": 0.5,
                "gr_clean": 30, "gr_shale": 120,
                "a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.05,
                "rho_matrix": 2.65, "dt_matrix": 55.5,
                "confidence": 0.3, "source": "default",
                "reasoning": "使用默认参数 (RAG未启用)"
            }

    def _step_interpret(self, state: WorkflowState, gas_file: str = None):
        """Step 4: 自动解释 (logInt run_workflow: QC→解释→矿物→沉积相)"""
        logger.info("[4/5] 自动解释")

        if self._log_int is None:
            from logInt import WellLogProcessor
            self._log_int = WellLogProcessor()

        processor = self._log_int

        # 应用推荐参数
        if state.parameter_recommendation:
            self._apply_params_to_processor(processor, state.parameter_recommendation)

        # ---- NaN 清洗: 真实测井数据常有空洞, 多矿物优化/孔隙度计算要求输入无 NaN ----
        # (IZZ0232 实测: 岩心/部分曲线 NaN 高达 72%, 直接 run_workflow 会 ValueError)
        try:
            import pandas as pd
            df = getattr(processor, 'data_processor', None)
            if df is not None:
                df = df.data
                if df is not None and isinstance(df, pd.DataFrame) and len(df):
                    num_cols = df.select_dtypes(include='number').columns
                    if len(num_cols):
                        df[num_cols] = df[num_cols].interpolate(
                            method='linear', limit_direction='both', axis=0)
                        df[num_cols] = df[num_cols].fillna(0.0)
                    logger.info(f"[4/5] NaN 清洗完成 ({len(num_cols)} 数值列)")
        except Exception as e:
            logger.warning(f"[4/5] NaN 清洗跳过: {e}")

        # 运行 logInt 完整解释工作流 (可传入气测文件)
        # 区域权威阿尔奇参数随 run_workflow 注入到其内部新建的分析器,
        # 以覆盖默认 0.05 与"水层反算"(rw_auto=False)
        results = processor.run_workflow(
            state.file_path, gas_file=gas_file,
            archie_params=state.parameter_recommendation,
        )
        if results is None:
            raise RuntimeError("logInt run_workflow 执行失败 (返回 None)")

        # 只保留摘要, 避免巨量曲线数据进入状态
        summary_keys = ['well_name', 'output_dir', 'report_path',
                        'visualization_results', 'density_curve_quality',
                        'density_porosity_priority']
        summary = {k: results[k] for k in summary_keys if k in results}

        # 提取关键解释结论 (若存在)
        for key in ('interpretation_conclusion', 'conclusion', 'facies_result'):
            if key in results:
                summary[key] = results[key]

        # 过度解释修剪 / 气测约束 / 区域流体先验 报告 —— 供经验沉淀与前端展示
        for key in ('over_interp_report', 'gas_constraint_report'):
            if key in results:
                summary[key] = results[key]

        # 解释结论分布 (层数统计, 用于经验沉淀与多次运行一致性对比)
        try:
            pdata = results.get('processed_data')
            if pdata is not None and 'INTERPRETATION' in pdata.columns:
                summary['interpretation_distribution'] = \
                    pdata['INTERPRETATION'].value_counts().to_dict()
        except Exception:
            pass

        state.interpretation_results = summary

        logger.info(f"  解释完成, 输出目录: {summary.get('output_dir', '未知')}")
        if summary.get('report_path'):
            logger.info(f"  报告: {summary['report_path']}")

    def _step_plot(self, state: WorkflowState):
        """Step 5: 收集图件与报告 (run_workflow 已生成, 此处汇总路径)"""
        logger.info("[5/5] 收集图件")

        results = state.interpretation_results or {}
        output_dir = results.get('output_dir') or self.output_dir

        # 收集输出目录中的图片
        plot_paths = []
        out = Path(output_dir)
        if out.exists():
            plot_paths = sorted(
                [str(p) for p in out.glob("*.png")]
                + [str(p) for p in out.glob("*.svg")]
            )

        state.plot_paths = plot_paths
        state.report_path = results.get('report_path', '')

        logger.info(f"  图件: {len(plot_paths)} 张, 报告: {state.report_path or '无'}")

    # ---------- 辅助方法 ----------

    @staticmethod
    def _collect_step_data(step_name: str, state: "WorkflowState") -> Dict:
        """收集步骤产出，回填到 StepResult.data 供前端读取"""
        if step_name == "load_data":
            return {
                "well_name": state.well_name,
                "region": state.region,
                "formation": state.formation,
                "profile_type": state.profile_type,
                "qc_report": state.qc_report,
                "curve_features": state.curve_features,
            }
        if step_name == "retrieve_knowledge":
            return {
                "region": state.region,
                "formation": state.formation,
                "context_available": state.interpretation_context is not None,
            }
        if step_name == "recommend_params":
            return dict(state.parameter_recommendation or {})
        if step_name == "interpret":
            return dict(state.interpretation_results or {})
        if step_name == "plot":
            return {
                "plot_paths": state.plot_paths,
                "report_path": state.report_path,
            }
        return {}

    def _extract_curve_features(self, data) -> Dict:
        """从数据中提取曲线特征"""
        features = {}
        try:
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                df = data
            elif hasattr(data, 'to_dataframe'):
                df = data.to_dataframe()
            elif isinstance(data, dict):
                df = pd.DataFrame.from_dict(data)
            else:
                return features

            curve_map = {
                'GR': ['GR', 'GR_EDTC', 'SGR', 'CGR', 'ECGR'],
                'RT': ['RT', 'RLLD', 'RD', 'AT90', 'M2RX', 'RLA5'],
                'DEN': ['DEN', 'RHOB', 'RHOZ', 'ZDEN', 'DENC'],
                'AC': ['AC', 'DT', 'DTCO', 'DTC', 'DT24'],
                'CNL': ['CNL', 'NPHI', 'TNPH', 'NPOR', 'NPHILS'],
                'SP': ['SP', 'SP_EDTC'],
                'CAL': ['CAL', 'CALI', 'HD', 'CALX'],
            }

            for target, candidates in curve_map.items():
                for col in candidates:
                    if col in df.columns:
                        series = pd.to_numeric(df[col], errors='coerce').dropna()
                        if len(series) > 0:
                            features[f"{target}_avg"] = round(series.mean(), 2)
                            features[f"{target}_min"] = round(series.min(), 2)
                            features[f"{target}_max"] = round(series.max(), 2)
                            features[f"{target}_std"] = round(series.std(), 2)
                        break
        except Exception as e:
            logger.debug(f"特征提取失败: {e}")

        return features

    def _detect_formation(self, features: Dict) -> str:
        """根据曲线特征推断层位类型"""
        gr = features.get('GR_avg', 60)
        rt = features.get('RT_avg', 20)
        den = features.get('DEN_avg', 2.5)

        if den > 2.7:
            return "碳酸盐岩段"
        elif gr > 80:
            return "泥岩段"
        elif gr < 50 and den < 2.45:
            return "砂岩段"
        else:
            return "砂泥岩互层"

    def _detect_profile_type(self, features: Dict) -> str:
        """推断剖面类型"""
        den = features.get('DEN_avg', 2.5)
        rt = features.get('RT_avg', 20)

        if den > 2.7 and rt > 30:
            return "carbonate"
        elif den < 2.45:
            return "sand_shale"
        else:
            return "mixed"

    def _apply_params_to_processor(self, processor, params: Dict):
        """将推荐参数应用到处理器

        注意: logInt 的阿尔奇参数读取位置是 config['archie']['Rw'/'a'/'m'/'n']
        (大写键, 嵌套子字典), 旧实现误写到顶层小写 'rw' 导致推荐值从未生效。
        此处同时写入 archie 子字典与顶层以兼容不同读取位置。
        """
        try:
            # 解释参数 -> DataProcessor
            dp = getattr(processor, 'data_processor', None)
            if dp is not None and hasattr(dp, 'config'):
                dp.config.update({
                    'vsh_method': params.get('vsh_method', 3),
                    'vsh_cutoff': params.get('vsh_cutoff', 0.5),
                })

            # 矿物/骨架参数 -> facies_analyzer.mineral_analyzer
            fa = getattr(processor, 'facies_analyzer', None)
            ma = getattr(fa, 'mineral_analyzer', None) if fa else getattr(processor, 'mineral_analyzer', None)
            if ma is not None and hasattr(ma, 'config'):
                # 1) 阿尔奇参数 (logInt 实际读取位置: config['archie']['Rw'] 等)
                arch = ma.config.setdefault('archie', {})
                arch.update({
                    'a': params.get('a', 1.0),
                    'm': params.get('m', 2.0),
                    'n': params.get('n', 2.0),
                    'Rw': params.get('rw', 0.05),
                    'Rsh': params.get('Rsh', 2.0),
                    'rho_matrix': params.get('rho_matrix', 2.65),
                    'dt_matrix': params.get('dt_matrix', 55.5),
                    # 饱和度方程(区域表可指定 indonesia/simandoux 等)
                    'method': params.get('method') or 'archie',
                })
                # 2) 区域命中权威 Rw 时关闭"水层反算", 避免被覆盖回错误值
                arch['rw_auto'] = not params.get('region_matched', False)
                # 2.5) 分层深度窗口 (按 MD 逐段应用各自 m/n/Rw)
                if params.get('formation_windows'):
                    arch['formation_windows'] = list(params['formation_windows'])
                # 3) 顶层也写一份 (兼容其它读取位置)
                ma.config.update({
                    'rw': params.get('rw', 0.05),
                    'a': params.get('a', 1.0),
                    'm': params.get('m', 2.0),
                    'n': params.get('n', 2.0),
                })
                logger.info(f"  应用阿尔奇参数到解释器: Rw={arch['Rw']}, "
                            f"a/m/n={arch['a']}/{arch['m']}/{arch['n']}, "
                            f"rw_auto={arch['rw_auto']}")
        except Exception as e:
            logger.debug(f"参数应用失败: {e}")

    # ---------- 钩子系统 ----------

    def on(self, event: str, callback: Callable):
        """注册事件钩子"""
        if event in self._hooks:
            self._hooks[event].append(callback)

    def _fire_hooks(self, event: str, step_name: str, **kwargs):
        for cb in self._hooks.get(event, []):
            try:
                cb(step_name, self._state, **kwargs)
            except Exception as e:
                logger.warning(f"钩子执行失败: {e}")

    # ---------- 持久化 ----------

    @staticmethod
    def _json_default(o):
        """JSON 序列化兜底: numpy/pandas 类型转 Python 原生"""
        import numpy as np
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, (np.bool_,)): return bool(o)
        if isinstance(o, (np.ndarray,)): return o.tolist()
        if hasattr(o, 'dtype') and hasattr(o, 'item'):  # pandas/numpy 标量兜底
            try: return o.item()
            except Exception: pass
        if hasattr(o, 'to_dict'):  # pandas Series
            return o.to_dict()
        try:
            from pandas import Timestamp
            if isinstance(o, Timestamp): return str(o)
        except Exception:
            pass
        return str(o)

    def _save_workflow_log(self, state: WorkflowState):
        """保存工作流运行日志"""
        log_file = Path(self.output_dir) / f"workflow_{state.well_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        log_data = {
            "well_name": state.well_name,
            "file_path": state.file_path,
            "region": state.region,
            "formation": state.formation,
            "profile_type": state.profile_type,
            "started_at": state.started_at,
            "curve_features": state.curve_features,
            "parameter_recommendation": state.parameter_recommendation,
            "steps": [asdict(s) for s in state.steps],
            "plot_paths": state.plot_paths,
            "report_path": state.report_path,
        }
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2,
                      default=self._json_default)
        logger.info(f"工作流日志已保存: {log_file}")

    def load_workflow_log(self, log_file: str) -> WorkflowState:
        """从日志恢复工作流状态"""
        with open(log_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        state = WorkflowState(
            well_name=data.get("well_name", ""),
            file_path=data.get("file_path", ""),
            region=data.get("region", ""),
            formation=data.get("formation", ""),
            profile_type=data.get("profile_type", ""),
            started_at=data.get("started_at", ""),
            curve_features=data.get("curve_features", {}),
            parameter_recommendation=data.get("parameter_recommendation", {}),
            plot_paths=data.get("plot_paths", []),
            report_path=data.get("report_path", ""),
        )
        state.steps = [StepResult(**s) for s in data.get("steps", [])]
        self._state = state
        return state

    def get_status(self) -> Dict:
        """获取当前状态摘要"""
        if self._state is None:
            return {"status": "idle"}

        state = self._state
        completed = [s.step_name for s in state.steps if s.status == "success"]
        failed = [s.step_name for s in state.steps if s.status == "failed"]

        return {
            "status": "running" if failed else ("completed" if len(completed) == 5 else "incomplete"),
            "well_name": state.well_name,
            "current_step": state.current_step,
            "completed_steps": completed,
            "failed_steps": failed,
            "total_duration_ms": sum(s.duration_ms for s in state.steps),
        }


# ============================================================
# 命令行入口
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="测井解释智能体编排器 - 五步自动化工作流"
    )

    parser.add_argument("file", nargs="?", help="LAS/DLIS 文件路径")
    parser.add_argument("--well", "-w", help="井名 (从文件提取默认)")
    parser.add_argument("--output", "-o", default="output", help="输出目录")
    parser.add_argument("--no-rag", action="store_true", help="禁用 RAG 知识增强")
    parser.add_argument("--no-vector", action="store_true", help="禁用向量检索")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--step", "-s", help="只运行指定步骤")
    parser.add_argument("--resume", "-r", help="从日志文件恢复")

    args = parser.parse_args()

    if args.resume:
        orch = WorkflowOrchestrator(output_dir=args.output)
        state = orch.load_workflow_log(args.resume)
        print(f"恢复工作流: {state.well_name}")
        # 继续未完成的步骤
        completed = {s.step_name for s in state.steps if s.status == "success"}
        for step in WorkflowOrchestrator.STEPS:
            if step not in completed:
                orch.run_step(step)
        return

    if not args.file:
        parser.print_help()
        return

    orch = WorkflowOrchestrator(
        output_dir=args.output,
        enable_rag=not args.no_rag,
        enable_vector=not args.no_vector,
    )

    if args.step:
        orch._state = WorkflowState(
            file_path=args.file,
            well_name=args.well or Path(args.file).stem,
            started_at=datetime.now().isoformat()
        )
        orch.run_step(args.step)
    else:
        state = orch.run(
            file_path=args.file,
            well_name=args.well,
            interactive=args.interactive,
        )

        # 打印摘要
        print(f"\n{'='*60}")
        print(f"工作流完成: {state.well_name}")
        for step in state.steps:
            icon = "✓" if step.status == "success" else "✗"
            print(f"  {icon} {step.step_name} ({step.duration_ms:.0f}ms)")
        print(f"输出目录: {args.output}")
        if state.plot_paths:
            print(f"图件: {len(state.plot_paths)} 张")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )
    main()
