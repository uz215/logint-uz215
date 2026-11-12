from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
from .graph_store import GraphStore


class KnowledgeAPI:
    def __init__(self, graph: GraphStore = None):
        if graph is None:
            self._gs = GraphStore()
        else:
            self._gs = graph

    def reload(self):
        self._gs.reload()

    def _follow(self, src_kind: str, src_name: str, rel: str, target_kind: str) -> List[str]:
        eid = self._gs._idx.get((src_kind, src_name))
        if eid is None:
            return []
        out_ids = self._gs.get_outgoing(eid, rel)
        out_names = []
        for oid in out_ids:
            e = self._gs.entities.get(oid)
            if e and e["kind"] == target_kind:
                out_names.append(e["name"])
        return list(dict.fromkeys(out_names))

    def _find_formation_direct(self, country: str, basin: str, fm_name: str):
        fm_name_clean = fm_name.strip().lower()
        for ent in self._gs.entities.values():
            if ent["kind"] != "formation":
                continue
            this_name = ent["name"].strip().lower()
            if this_name != fm_name_clean:
                continue
            props = ent["props"]
            if props.get("country") == country and props.get("basin") == basin:
                return ent
        return None

    def _get_methods_from_formation(self, fm_ent: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        fm_eid = fm_ent["id"]
        method_eids = self._gs.get_outgoing(fm_eid, "has_interp_method")
        for mid in method_eids:
            m_ent = self._gs.entities.get(mid)
            if not m_ent:
                continue
            mp = m_ent["props"]
            out.append({
                "method_name": m_ent["name"],
                "formula": mp.get("formula", ""),
                "threshold": mp.get("threshold", {}),
                "condition": mp.get("condition", ""),
                "log_response": mp.get("log_response", {}),
                "source": mp.get("source", "")
            })
        legacy_name = fm_ent["props"].get("interpretation_method")
        if legacy_name and not out:
            m_ent = self._gs.lookup("interpretation_method", legacy_name)
            if m_ent:
                mp = m_ent["props"]
                out.append({
                    "method_name": m_ent["name"],
                    "formula": mp.get("formula", ""),
                    "threshold": mp.get("threshold", {}),
                    "condition": mp.get("condition", ""),
                    "log_response": mp.get("log_response", {}),
                    "source": mp.get("source", "")
                })
        return out

    def lookup_hierarchy(self, country: str) -> Dict[str, Any]:
        out = {"country": country, "basins": []}
        basins = self._follow("country", country, "contains", "basin")
        for b in basins:
            sags = self._follow("basin", b, "contains", "sag")
            blocks = self._follow("basin", b, "contains", "block")
            oilfields = self._follow("basin", b, "contains", "oilfield")
            of_list = []
            for of in oilfields:
                fms = self._follow("oilfield", of, "has_formation", "formation")
                wells = self._follow("oilfield", of, "has_well", "well")
                of_list.append({"name": of, "formations": fms, "wells": wells})
            out["basins"].append({
                "name": b,
                "sags": sags,
                "blocks": blocks,
                "oilfields": of_list
            })
        return out

    def lookup_interp_method(
        self,
        country: str,
        basin: Optional[str] = None,
        formation: Optional[str] = None
    ) -> Dict[str, Any]:
        result = {"ok": False, "msg": "未找到该地层参数", "methods": []}
        if self._gs.lookup("country", country) is None:
            result["msg"] = "未找到该国家"
            return result

        if basin is not None and formation is not None:
            fm_ent = self._find_formation_direct(country, basin, formation)
            if fm_ent is None:
                return result
            methods = self._get_methods_from_formation(fm_ent)
            if methods:
                return {"ok": True, "msg": "查询成功", "methods": methods}
            else:
                return {"ok": True, "msg": "找到地层，暂无绑定解释方法", "methods": []}

        target_fms: List[str] = []
        if basin is not None:
            oilfields = self._follow("basin", basin, "contains", "oilfield")
            for of in oilfields:
                target_fms.extend(self._follow("oilfield", of, "has_formation", "formation"))
        else:
            basins = self._follow("country", country, "contains", "basin")
            for b in basins:
                oilfields = self._follow("basin", b, "contains", "oilfield")
                for of in oilfields:
                    target_fms.extend(self._follow("oilfield", of, "has_formation", "formation"))

        for fm_name in list(dict.fromkeys(target_fms)):
            fm_ent = self._gs.lookup("formation", fm_name)
            if fm_ent:
                result["methods"].extend(self._get_methods_from_formation(fm_ent))
        if result["methods"]:
            result["ok"] = True
            result["msg"] = "查询成功"
        return result

    def match_methods(
        self,
        country: str,
        basin: str,
        formation: str,
        value: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        raw = self.lookup_interp_method(country, basin, formation)
        if not raw["ok"]:
            return raw
        matched = []
        for m in raw["methods"]:
            th = m.get("threshold", {})
            pass_flag = True
            if value is not None:
                for k, lim in th.items():
                    if k not in value:
                        continue
                    v = value[k]
                    lo = lim.get("min")
                    hi = lim.get("max")
                    if lo is not None and v < lo:
                        pass_flag = False
                    if hi is not None and v > hi:
                        pass_flag = False
            if pass_flag:
                matched.append(m)
        if matched:
            return {"ok": True, "msg": "匹配成功", "matched": matched}
        else:
            return {"ok": True, "msg": "找到地层，但测井值不在阈值区间", "matched": []}


_api_inst = KnowledgeAPI()


def lookup_interp_method(country: str, basin: Optional[str] = None, formation: Optional[str] = None):
    return _api_inst.lookup_interp_method(country, basin, formation)


def match_methods(country: str, basin: str, formation: str, value: Optional[Dict[str, float]] = None):
    return _api_inst.match_methods(country, basin, formation, value)


def lookup_hierarchy(country: str):
    return _api_inst.lookup_hierarchy(country)


def get_kb_stats():
    gs = _api_inst._gs
    cnt = {
        "country": 0,
        "basin": 0,
        "sag": 0,
        "block": 0,
        "oilfield": 0,
        "formation": 0,
        "well": 0,
        "interpretation_method": 0
    }
    for e in gs.entities.values():
        if e["kind"] in cnt:
            cnt[e["kind"]] += 1
    cnt["fact"] = len(gs.facts)
    cnt["entity_total"] = len(gs.entities)
    return cnt
