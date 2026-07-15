# -*- coding: utf-8 -*-
"""城市名 ↔ 飞猪城市三字码映射（F1 用）。

飞猪 listingsearch 深链需要城市三字码 depCityCode/arrCityCode（如北京=BJS）。
这里内置常用国内 + 国际城市；`intl=True` 标记国际/港澳台（决定走国际列表页）。
未命中的城市，前端也允许直接输入三字码。
"""

# name -> (code, intl)  ；code 为飞猪城市码（多机场城市用城市码，如北京 BJS 含 PEK/PKX）
CITIES = {
    # ---- 国内主要城市 ----
    "北京": ("BJS", False), "上海": ("SHA", False), "广州": ("CAN", False),
    "深圳": ("SZX", False), "杭州": ("HGH", False), "成都": ("CTU", False),
    "重庆": ("CKG", False), "西安": ("SIA", False), "南京": ("NKG", False),
    "武汉": ("WUH", False), "长沙": ("CSX", False), "青岛": ("TAO", False),
    "厦门": ("XMN", False), "昆明": ("KMG", False), "大连": ("DLC", False),
    "天津": ("TSN", False), "郑州": ("CGO", False), "三亚": ("SYX", False),
    "海口": ("HAK", False), "贵阳": ("KWE", False), "南宁": ("NNG", False),
    "沈阳": ("SHE", False), "哈尔滨": ("HRB", False), "长春": ("CGQ", False),
    "济南": ("TNA", False), "福州": ("FOC", False), "南昌": ("KHN", False),
    "太原": ("TYN", False), "乌鲁木齐": ("URC", False), "兰州": ("LHW", False),
    "宁波": ("NGB", False), "温州": ("WNZ", False), "无锡": ("WUX", False),
    "珠海": ("ZUH", False), "呼和浩特": ("HET", False), "银川": ("INC", False),
    "西宁": ("XNN", False), "拉萨": ("LXA", False), "石家庄": ("SJW", False),
    # ---- 港澳台 ----
    "香港": ("HKG", True), "澳门": ("MFM", True), "台北": ("TPE", True),
    "高雄": ("KHH", True), "台中": ("RMQ", True),
    # ---- 国际（东亚/东南亚为主）----
    "东京": ("TYO", True), "大阪": ("OSA", True), "名古屋": ("NGO", True),
    "福冈": ("FUK", True), "札幌": ("SPK", True), "冲绳": ("OKA", True),
    "首尔": ("SEL", True), "釜山": ("PUS", True), "济州": ("CJU", True),
    "曼谷": ("BKK", True), "普吉": ("HKT", True), "清迈": ("CNX", True),
    "新加坡": ("SIN", True), "吉隆坡": ("KUL", True), "巴厘岛": ("DPS", True),
    "雅加达": ("JKT", True), "马尼拉": ("MNL", True), "胡志明市": ("SGN", True),
    "河内": ("HAN", True), "金边": ("PNH", True), "仰光": ("RGN", True),
    "迪拜": ("DXB", True), "多哈": ("DOH", True), "伦敦": ("LON", True),
    "巴黎": ("PAR", True), "法兰克福": ("FRA", True), "阿姆斯特丹": ("AMS", True),
    "罗马": ("ROM", True), "纽约": ("NYC", True), "洛杉矶": ("LAX", True),
    "旧金山": ("SFO", True), "西雅图": ("SEA", True), "温哥华": ("YVR", True),
    "多伦多": ("YTO", True), "悉尼": ("SYD", True), "墨尔本": ("MEL", True),
    "奥克兰": ("AKL", True), "莫斯科": ("MOW", True),
}

# code -> name（反查，展示用）
CODE_TO_NAME = {code: name for name, (code, _) in CITIES.items()}


def resolve(text):
    """把用户输入（城市名或三字码）解析为 (code, name, intl)。解析不出返回 None。"""
    if not text:
        return None
    t = text.strip()
    if t in CITIES:
        code, intl = CITIES[t]
        return code, t, intl
    up = t.upper()
    if up in CODE_TO_NAME:
        # 直接给了三字码：国际性未知，按是否在国内城市集合里推断
        name = CODE_TO_NAME[up]
        intl = CITIES[name][1]
        return up, name, intl
    if len(up) == 3 and up.isalpha():
        # 未知的三字码，放行（国际性未知，默认按国际列表页更兼容）
        return up, up, True
    return None


def city_list():
    """给前端做下拉/联想用：[{name, code, intl}]。"""
    return [{"name": n, "code": c, "intl": i} for n, (c, i) in CITIES.items()]
