"""
多语言翻译与检测模块
支持中/英/西/俄/葡语言检测与术语翻译
用于增强 logIntKnowledge.py 中的 Translator
"""

try:
    from langdetect import detect, detect_langs
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False


class MultiLanguageTranslator:
    """多语言翻译工具，支持中/英/西/俄/葡检测与术语翻译为中文"""

    def __init__(self):
        self.supported_languages = ['zh', 'en', 'es', 'ru', 'pt']
        self.term_dict = self._build_term_dict()

    def _build_term_dict(self):
        return {
            'zh_en': {
                '测井': 'logging', '录井': 'mud logging', '孔隙度': 'porosity',
                '渗透率': 'permeability', '电阻率': 'resistivity',
                '含水饱和度': 'water saturation', '泥质含量': 'shale volume',
                '阿尔奇公式': 'Archie equation', '自然伽马': 'gamma ray',
                '声波时差': 'sonic transit time', '密度': 'density',
                '中子': 'neutron', '油层': 'oil layer', '气层': 'gas layer',
                '水层': 'water layer', '储层': 'reservoir', '砂岩': 'sandstone',
                '泥岩': 'shale', '碳酸盐岩': 'carbonate', '油田': 'oil field',
                '区块': 'block', '构造': 'structure', '井': 'well',
                '深度': 'depth', '地层': 'formation', '岩性': 'lithology',
                '试油': 'well testing', '生产': 'production', '测井系列': 'logging suite'
            },
            'en_zh': {
                'logging': '测井', 'mud logging': '录井', 'porosity': '孔隙度',
                'permeability': '渗透率', 'resistivity': '电阻率',
                'water saturation': '含水饱和度', 'shale volume': '泥质含量',
                'Archie equation': '阿尔奇公式', 'gamma ray': '自然伽马',
                'sonic transit time': '声波时差', 'density': '密度',
                'neutron': '中子', 'oil layer': '油层', 'gas layer': '气层',
                'water layer': '水层', 'reservoir': '储层', 'sandstone': '砂岩',
                'shale': '泥岩', 'carbonate': '碳酸盐岩', 'oil field': '油田',
                'block': '区块', 'structure': '构造', 'well': '井',
                'depth': '深度', 'formation': '地层', 'lithology': '岩性',
                'well testing': '试油', 'production': '生产', 'logging suite': '测井系列'
            },
            'es_zh': {
                'registro': '测井', 'porosidad': '孔隙度', 'permeabilidad': '渗透率',
                'resistividad': '电阻率', 'saturación de agua': '含水饱和度',
                'volumen de arcilla': '泥质含量', 'arenisca': '砂岩',
                'lutita': '泥岩', 'caliza': '石灰岩', 'dolomía': '白云岩',
                'yacimiento': '储层', 'pozo': '井', 'campo petrolífero': '油田',
                'formación': '地层', 'profundidad': '深度', 'densidad': '密度',
                'neutrón': '中子', 'perfilaje': '测井', 'registro de pozo': '测井',
                'registros eléctricos': '电法测井', 'registro por inducción': '感应测井',
                'registro de densidad': '密度测井', 'registro de neutrones': '中子测井'
            },
            'ru_zh': {
                'каротаж': '测井', 'пористость': '孔隙度', 'проницаемость': '渗透率',
                'удельное сопротивление': '电阻率', 'водонасыщенность': '含水饱和度',
                'глинистость': '泥质含量', 'песчаник': '砂岩', 'глинистый': '泥岩',
                'известняк': '石灰岩', 'доломит': '白云岩', 'пласт': '地层',
                'скважина': '井', 'месторождение': '油田', 'нефть': '石油',
                'газ': '天然气', 'глубина': '深度', 'плотность': '密度',
                'нейтронный': '中子', 'гамма-каротаж': '自然伽马',
                'электрокаротаж': '电法测井', 'индукционный каротаж': '感应测井',
                'плотностной каротаж': '密度测井', 'нейтронный каротаж': '中子测井'
            },
            'pt_zh': {
                'perfuração': '测井', 'porosidade': '孔隙度', 'permeabilidade': '渗透率',
                'resistividade': '电阻率', 'saturação de água': '含水饱和度',
                'volume de argila': '泥质含量', 'arenito': '砂岩', 'xisto': '泥岩',
                'calcário': '石灰岩', 'dolomita': '白云岩', 'reservatório': '储层',
                'poço': '井', 'campo de petróleo': '油田', 'formação': '地层',
                'profundidade': '深度', 'densidade': '密度', 'neutrônico': '中子',
                'raio gama': '自然伽马', 'perfilagem': '测井',
                'perfis elétricos': '电法测井', 'perfis de indução': '感应测井',
                'perfis de densidade': '密度测井', 'perfis de nêutrons': '中子测井'
            }
        }

    def detect_language(self, text):
        """检测文本语言"""
        if not text or len(text.strip()) < 20:
            return 'unknown'
        if LANGDETECT_AVAILABLE:
            try:
                detected = detect(text[:2000])
                if detected in ('zh-cn', 'zh-tw', 'zh'):
                    return 'zh'
                if detected in self.supported_languages:
                    return detected
                return detected
            except Exception:
                pass
        text_sample = text[:2000]
        zh = sum(1 for c in text_sample if '\u4e00' <= c <= '\u9fff')
        en = sum(1 for c in text_sample if 'a' <= c.lower() <= 'z')
        es_pt = sum(1 for c in text_sample if c.lower() in 'áéíóúñüãõç')
        ru = sum(1 for c in text_sample if '\u0400' <= c <= '\u04ff')
        total = len(text_sample)
        if zh > total * 0.05:
            return 'zh'
        if ru > total * 0.05:
            return 'ru'
        if es_pt > 3:
            return 'es'
        if en > total * 0.3:
            return 'en'
        return 'unknown'

    def translate_to_chinese(self, text, source_lang=None):
        """将文本翻译为中文，优先使用术语词典替换"""
        if not text:
            return text
        if source_lang is None:
            source_lang = self.detect_language(text)
        if source_lang in ('zh', 'unknown'):
            return text
        dict_key = f"{source_lang}_zh"
        terms = self.term_dict.get(dict_key, {})
        result = text
        replaced = False
        for term, trans in sorted(terms.items(), key=lambda x: len(x[0]), reverse=True):
            if term in result.lower():
                result = result.replace(term, trans)
                result = result.replace(term.capitalize(), trans)
                result = result.replace(term.upper(), trans)
                replaced = True
        if not replaced:
            result = f"[原文语言: {source_lang}]\n{text}"
        else:
            result = f"[原文语言: {source_lang}, 已术语翻译]\n{result}\n\n[原文参考]:\n{text[:500]}..."
        return result

    def translate(self, text, target_lang='zh'):
        if target_lang == 'zh':
            return self.translate_to_chinese(text)
        return text
