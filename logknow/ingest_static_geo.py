# -*- coding: utf-8 -*-
"""
ingest_static_geo.py
将 logknow/static_geo/{continent}/{country}.json 的区域测井知识入库到 logknow 知识库
（持久化于 logknow/data/graph_store.json，复用 bootstrap_knowledge.GraphStore 模型）。

设计要点（与存量体系严格对齐，非破坏性、可重复运行）：
- 复用 bootstrap_knowledge.GraphStore：add_node 合并 props、add_edge 幂等去重。
- country 按别名归并：孟加拉→孟加拉国、阿拉伯联合酋长国→阿联酋；其余同名合并、新国创建。
- 凹陷(sag)/区块(block) 以 “盆地·名” 命名空间，避免跨盆地重名（如“中央凹陷”在印尼/中国各一）碰撞。
- 解释方法(method) 与存量合并：applicable_formations / applicable_regions 取并集，不覆盖已有权威字段。
- 仅追加，不删除已有 30 国 BENCHMARK 数据。
"""
import sys
import json
import glob
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logknow.bootstrap_knowledge import GraphStore

BASE = Path(__file__).resolve().parent
STATIC_GEO = BASE / "static_geo"

CONTINENT_CN = {
    "africa": "非洲",
    "asia": "亚洲",
    "europe": "欧洲",
    "north_america": "北美洲",
    "oceania": "大洋洲",
    "south_america": "南美洲",
}

# 国家别名归并（static_geo 写法 → 存量 BENCHMARK 正典写法）
COUNTRY_CANON = {
    "孟加拉": "孟加拉国",
    "阿拉伯联合酋长国": "阿联酋",
}

# 自动归一：优先用 region_normalize.yaml 权威别名表，失败兜底 COUNTRY_CANON
try:
    from logknow.region_normalizer import RegionNormalizer
    _RN = RegionNormalizer()
    def _canon_country(name):
        return _RN.normalize_country(name) or COUNTRY_CANON.get(name, name)
except Exception:
    _RN = None
    def _canon_country(name):
        return COUNTRY_CANON.get(name, name)


def resolve_country(gs, name, continent):
    """返回 (节点名, 是否新建)。按别名归并存量节点；不存在则新建。"""
    canon = _canon_country(name)
    existing = None
    for nd in gs.nodes.values():
        if nd["type"] != "country":
            continue
        if nd["name"] == canon or canon in nd.get("props", {}).get("aliases", []):
            existing = nd
            break
    if existing:
        key = existing["name"]
        props = dict(existing.get("props", {}))
        props["continent"] = continent
        if name != canon and name not in props.get("aliases", []):
            props.setdefault("aliases", []).append(name)
        gs.add_node("country", key, props)
        return key, False
    aliases = [name] if name != canon else []
    gs.add_node("country", canon, {"continent": continent, "aliases": aliases})
    return canon, True


def ingest(gs, dry_run=False):
    files = sorted(glob.glob(str(STATIC_GEO / "**" / "*.json"), recursive=True))
    n_files = 0
    n_records = 0
    new_countries = []
    merged_countries = []
    methods_seen = set()
    edge_count0 = len(gs.edges)

    for f in files:
        rel = Path(f).relative_to(STATIC_GEO)
        parts = rel.parts
        continent = CONTINENT_CN.get(parts[0], parts[0])
        raw = json.loads(Path(f).read_text(encoding="utf-8-sig"))
        recs = raw if isinstance(raw, list) else [raw]
        for rec in recs:
            n_records += 1
            country = rec["country"]
            basin = rec["basin"]
            sag = rec.get("sag", "")
            block = rec.get("block", "")
            oilfield = rec["oilfield"]
            well = rec.get("well", "")
            formation = rec["formation"]
            structure = rec.get("structure", "")
            method_name = rec.get("method_name", "")
            method_meta = rec.get("method_meta", {}) or {}
            strata_meta = rec.get("strata_meta", {}) or {}
            gwc = rec.get("gwc", {}) or {}

            ckey, is_new = resolve_country(gs, country, continent)
            if is_new:
                new_countries.append(country)
            else:
                merged_countries.append((country, ckey))

            gs.add_node("basin", basin, {})
            gs.add_edge("country", ckey, "contains", "basin", basin)

            if sag:
                sag_key = f"{basin}·{sag}"
                gs.add_node("sag", sag_key, {"basin": basin})
                gs.add_edge("basin", basin, "contains", "sag", sag_key)
            if block:
                block_key = f"{basin}·{block}"
                gs.add_node("block", block_key, {"basin": basin})
                gs.add_edge("basin", basin, "contains", "block", block_key)

            gs.add_node("oilfield", oilfield, {"structure": structure})
            gs.add_edge("basin", basin, "contains", "oilfield", oilfield)

            # formation 节点：携带地层/测井响应/油气类型/构造/油水界面
            fm_props = {
                "sub_layer": strata_meta.get("sub_layer", ""),
                "lithology": strata_meta.get("lithology", []),
                "log_response": strata_meta.get("log_response", {}),
                "hydrocarbon_type": strata_meta.get("hydrocarbon_type", ""),
                "structure": structure,
                "gwc": gwc,
                "country": ckey,
                "basin": basin,
            }
            gs.add_node("formation", formation, fm_props)
            gs.add_edge("oilfield", oilfield, "has_formation", "formation", formation)

            if well:
                gs.add_node("well", well, {})
                gs.add_edge("oilfield", oilfield, "has_well", "well", well)

            # 解释方法：与存量合并（applicable_formations/regions 取并集）
            if method_name:
                methods_seen.add(method_name)
                existing = gs.lookup("interpretation_method", method_name)
                af = set(method_meta.get("applicable_formations", []))
                ar = set(method_meta.get("applicable_regions", []))
                af.add(formation)
                ar.add(ckey)
                if existing:
                    props = dict(existing.get("props", {}))
                    af |= set(props.get("applicable_formations", []))
                    ar |= set(props.get("applicable_regions", []))
                    props.update(method_meta)
                else:
                    props = dict(method_meta)
                props["method_name"] = method_name
                props["applicable_formations"] = sorted(af)
                props["applicable_regions"] = sorted(ar)
                gs.add_node("interpretation_method", method_name, props)
                gs.add_edge(
                    "interpretation_method", method_name,
                    "applicable_to", "formation", formation
                )
        n_files += 1

    return {
        "n_files": n_files,
        "n_records": n_records,
        "new_countries": sorted(set(new_countries)),
        "merged_countries": merged_countries,
        "methods_seen": sorted(methods_seen),
        "edges_added": len(gs.edges) - edge_count0,
    }


def main():
    gs = GraphStore()
    before = len(gs.nodes)
    summary = ingest(gs)
    gs._save()
    after = len(gs.nodes)
    print(f"✅ 入库完成：读取 {summary['n_files']} 文件 / {summary['n_records']} 条记录")
    print(f"   图谱节点：{before} → {after}（新增 {after - before}）")
    print(f"   新增关系边：{summary['edges_added']}")
    print(f"   新建国家（存量无）：{summary['new_countries'] or '无'}")
    true_merges = [(o, k) for (o, k) in summary['merged_countries'] if o != k]
    print(f"   按别名归并国家：{true_merges or '无'}")
    print(f"   涉及解释方法：{len(summary['methods_seen'])} 个")
    from logknow.bootstrap_knowledge import GRAPH_FILE
    print(f"📁 持久化路径：{GRAPH_FILE}")


if __name__ == "__main__":
    main()
