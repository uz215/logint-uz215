# logknow/region_normalizer.py
import yaml
import re
from pathlib import Path
from typing import Optional, List

CONFIG_PATH = Path(__file__).resolve().parent / "region_normalize.yaml"


class RegionNormalizer:
    def __init__(self, config_path: Optional[Path] = None):
        cfg_path = config_path or CONFIG_PATH
        with open(cfg_path, "r", encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)
        self.country_map = self._build_country_lookup()
        self.term_map = self._build_term_lookup()
        # 原始英文->中文，按长度降序供短语替换（长词优先，避免 "sandstone" 抢先命中）
        self.term_pairs = sorted(
            [(str(en), str(cn)) for en, cn in (self.cfg.get("term_mapping") or {}).items()],
            key=lambda x: -len(x[0]))
        self.hierarchy = self.cfg["geo_hierarchy"]["order"]

    @staticmethod
    def _key(s) -> str:
        """归一匹配键：忽略大小写、空格/下划线/连字符/点/括号差异，
        使 'South Sudan' / 'south_sudan' / 'SOUTH-SUDAN' 命中同一中文正典。"""
        return re.sub(r'[\s_\-\.\u00b7()（）]', '', str(s).strip().lower())

    def _build_country_lookup(self):
        lookup = {}
        for main, item in self.cfg["country_mapping"].items():
            lookup[self._key(main)] = main
            for alias in item.get("aliases", []):
                lookup[self._key(alias)] = main
        return lookup

    def _build_term_lookup(self):
        lookup = {}
        for en, cn in (self.cfg.get("term_mapping") or {}).items():
            lookup[self._key(en)] = cn
        return lookup

    def normalize_country(self, raw_name: str) -> Optional[str]:
        """外文国名 -> 中文正典名；已是中文正典则原样返回；未收录返回 None。"""
        if not raw_name:
            return None
        return self.country_map.get(self._key(raw_name))

    def normalize_term(self, raw_name: str) -> Optional[str]:
        """外文通用术语 -> 中文规范名；未收录返回 None（专名保留原文）。"""
        if not raw_name:
            return None
        return self.term_map.get(self._key(raw_name))

    def normalize_phrase(self, text: str) -> Optional[str]:
        """整串字段的英->中归一：按词边界替换其中的英文通用术语（长词优先），
        并去掉中文之间的空格，使 'Cambro-Ordovician sandstone reservoir' 与
        '寒武-奥陶系砂岩储层' 收敛到同一 canonical。无替换返回 None。"""
        if not text:
            return None
        out = str(text)
        changed = False
        for en, cn in self.term_pairs:
            pat = re.compile(r'(?<![A-Za-z])' + re.escape(en) + r'(?![A-Za-z])', re.I)
            out, n = pat.subn(cn, out)
            if n:
                changed = True
        if not changed:
            return None
        out = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', out)
        return out.strip()

    def get_geo_order(self):
        return self.hierarchy

    def match_sag_text(self, text: str) -> bool:
        kw = self.cfg["extract_patterns"]["sag_keywords"]
        return any(re.search(pat, text, re.IGNORECASE) for pat in kw)

    def match_structure_text(self, text: str) -> bool:
        kw = self.cfg["extract_patterns"]["structure_keywords"]
        return any(re.search(pat, text, re.IGNORECASE) for pat in kw)

    def get_required_fields(self, entity_type: str) -> List[str]:
        return self.cfg["required_fields"].get(entity_type, [])


if __name__ == "__main__":
    rn = RegionNormalizer()
    print(rn.normalize_country("乌兹别克"))
    print(rn.normalize_country("哈萨克"))
    print(rn.get_geo_order())
