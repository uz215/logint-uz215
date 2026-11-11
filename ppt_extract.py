# -*- coding: utf-8 -*-
"""老版.ppt二进制文本提取(类似doc)"""
import sys, re
sys.path.insert(0, r'F:\360\src')

def extract_ppt_binary(path):
    data = open(path, 'rb').read()
    # 方式1: UTF-16
    result = []
    cur = []
    for i in range(0, len(data) - 1, 2):
        code = int.from_bytes(data[i:i+2], 'little')
        if (0x20 <= code <= 0x7E) or (0x3000 <= code <= 0x9FFF) or (0xFF00 <= code <= 0xFFEF):
            cur.append(chr(code))
        else:
            if len(cur) >= 6:
                result.append(''.join(cur))
            cur = []
    if len(cur) >= 6:
        result.append(''.join(cur))
    txt16 = '\n'.join(result)
    # 方式2: GBK
    t = data.decode('gbk', errors='ignore').replace('\x00', '')
    lines = [l.strip() for l in t.split('\r') if len(l.strip()) >= 3 and
             re.search(r'[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2,}', l)]
    txt_gbk = '\n'.join(lines)
    # 方式3: ASCII
    cur = []
    result2 = []
    for b in data:
        if 0x20 <= b <= 0x7E:
            cur.append(chr(b))
        else:
            if len(cur) >= 12:
                result2.append(''.join(cur))
            cur = []
    if len(cur) >= 12:
        result2.append(''.join(cur))
    txt_ascii = '\n'.join(result2)
    # 选择: 统计中文字符数判断
    cn16 = len(re.findall(r'[\u4e00-\u9fff]', txt16))
    cngbk = len(re.findall(r'[\u4e00-\u9fff]', txt_gbk))
    print('[统计] UTF16中文:', cn16, ' GBK中文:', cngbk, ' ASCII长度:', len(txt_ascii))
    if cn16 > cngbk * 2:
        return txt16
    if cngbk > cn16:
        return txt_gbk
    return txt_ascii if len(txt_ascii) > len(txt16) else txt16

if __name__ == '__main__':
    for p in sys.argv[1:]:
        print('=' * 40)
        print(p)
        t = extract_ppt_binary(p)
        print(t[:3500])
