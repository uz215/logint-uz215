# logknow/region_normalizer.py
import yaml
import re
from pathlib import Path
from typing import Optional, List

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "region_normalize.yaml"


class RegionNormalizer:
    def __init__(self, config_path: Optional[Path] = None):
        cfg_path = config_path or CONFIG_PATH
        with open(cfg_path, "r", encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)
        self.country_map = self._build_country_lookup()
        self.hierarchy = self.cfg["geo_hierarchy"]["order"]

    def _build_country_lookup(self):
        lookup = {}
        for main, item in self.cfg["country_mapping"].items():
            lookup[main] = main
            for alias in item.get("aliases", []):
                lookup[alias] = main
        return lookup

    def normalize_country(self, raw_name: str) -> Optional[str]:
        if not raw_name:
            return None
        raw = raw_name.strip()
        return self.country_map.get(raw, None)

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
