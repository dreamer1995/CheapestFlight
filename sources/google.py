# -*- coding: utf-8 -*-
"""Google Flights 数据源：单次 HTTP 抓取（无登录、无浏览器，经代理走境外 IP，快而稳）。

用 fast_flights 构造 tfs 查询 URL，`requests` 直接取 HTML，解析航班 `aria-label`
（中文、含人民币价格）为与 fliggy 相同的归一化航班对象，前端零改动复用。

价格口径提醒：Google 显示的是航司挂牌起价那一类，**不含中国 OTA 折扣舱**，
故国内航线价格通常高于飞猪；国际航线较有竞争力。
"""
import re
from datetime import date as _date, datetime

import requests
from fast_flights import FlightQuery, Passengers, create_query

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_MONTHS = {f"{c}月": i + 1 for i, c in enumerate(
    ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"])}


def _short_airport(name):
    """北京首都国际机场 -> 首都；杭州萧山国际机场 -> 萧山（尽量取机场标识名）。"""
    if not name:
        return name
    s = name
    for suf in ("国际机场", "机场"):
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    # 去掉前缀城市名（常见 2~3 字），启发式：若剩余仍很长，保留后半
    return s


def _parse_md(month_cn, day):
    m = _MONTHS.get(month_cn)
    return (m, int(day)) if m else None


def _label_to_flight(label, dep_code, arr_code, search_date):
    """把一条 Google 航班 aria-label 解析为归一化航班；解析不出返回 None。"""
    # 价格
    mp = re.search(r"起价[：:]\s*([\d,]+)\s*人民币", label)
    if not mp:
        return None
    price = int(mp.group(1).replace(",", ""))

    # 航司 + 直飞/中转
    direct = "直达航班" in label
    mt = re.search(r"中间经停\s*(\d+)\s*站", label)
    transfer_count = int(mt.group(1)) if mt else 0
    is_transfer = transfer_count > 0 or not direct and mt is not None
    ma = re.search(r"人民币。\s*(.+?)(?:直达航班|航班，中间经停)", label)
    airline = ma.group(1).strip("， 。") if ma else ""

    # 起飞 / 到达： "星期五, 七月 17 06:55 离开北京首都国际机场"
    md = re.search(r"([一二三四五六七八九十]+月)\s*(\d+)\s*(\d{1,2}:\d{2})\s*离开(\S+?机场)", label)
    mr = re.search(r"([一二三四五六七八九十]+月)\s*(\d+)\s*(\d{1,2}:\d{2})\s*到达(\S+?机场)", label)
    if not md or not mr:
        return None
    dep_md = _parse_md(md.group(1), md.group(2))
    arr_md = _parse_md(mr.group(1), mr.group(2))
    dep_time_hm, arr_time_hm = md.group(3), mr.group(3)
    dep_airport, arr_airport = md.group(4), mr.group(4)

    # 用搜索日期年份组装 datetime，跨天由 dep/arr 月日推算
    try:
        y = int(search_date[:4])
    except Exception:
        y = datetime.now().year
    dep_dt = datetime.strptime(f"{search_date} {dep_time_hm}", "%Y-%m-%d %H:%M")
    arr_year = y
    if arr_md and dep_md and (arr_md[0] < dep_md[0]):  # 跨年
        arr_year = y + 1
    arr_d = _date(arr_year, arr_md[0], arr_md[1]) if arr_md else dep_dt.date()
    arr_dt = datetime(arr_d.year, arr_d.month, arr_d.day,
                      int(arr_time_hm.split(":")[0]), int(arr_time_hm.split(":")[1]))
    cross_days = (arr_dt.date() - dep_dt.date()).days

    # 时长
    dur = None
    mdur = re.search(r"总时长\s*(?:(\d+)\s*小时)?\s*(?:(\d+)\s*分钟)?", label)
    if mdur and (mdur.group(1) or mdur.group(2)):
        dur = int(mdur.group(1) or 0) * 60 + int(mdur.group(2) or 0)

    # 中转地： "在大连市的大连周水子国际机场用时 2小时的转机"（机场名可能是繁体機場/英文）
    stops = []
    for sm in re.finditer(r"在(.+?)的(.+?)用时\s*(.+?)的转机", label):
        stops.append({"cityName": sm.group(1).rstrip("市"),
                      "airportName": sm.group(2).strip(), "airportCode": None,
                      "layover": sm.group(3).strip()})
    if not stops and transfer_count:
        is_transfer = True

    def _dt_str(dt):
        return dt.strftime("%Y-%m-%d %H:%M:00")

    return {
        "id": f"G_{search_date}_{dep_code}_{arr_code}_{dep_time_hm}_{airline}_{price}",
        "type": "transfer" if (is_transfer or transfer_count) else "direct",
        "depDate": search_date,
        "depTime": _dt_str(dep_dt),
        "arrTime": _dt_str(arr_dt),
        "crossDays": cross_days,
        "durationMin": dur,
        "transferCount": transfer_count,
        "dep": {"cityName": None, "cityCode": dep_code,
                "airportName": dep_airport, "airportShortName": _short_airport(dep_airport),
                "airportCode": dep_code, "term": ""},
        "arr": {"cityName": None, "cityCode": arr_code,
                "airportName": arr_airport, "airportShortName": _short_airport(arr_airport),
                "airportCode": arr_code, "term": ""},
        "stops": stops,
        "segments": [],
        "airlines": [airline] if airline else [],
        "flightNos": "",
        "price": price,
        "salePrice": price,
        "tax": None,
    }


def search(dep_code, arr_code, date, adults=1, dep_name="", arr_name="", **_):
    """抓 Google Flights 单程。返回 {flights, lowestPrice, count, login_needed:False}。"""
    url = create_query(
        flights=[FlightQuery(date=date, from_airport=dep_code, to_airport=arr_code)],
        trip="one-way", seat="economy", passengers=Passengers(adults=adults),
        currency="CNY", language="zh-CN",
    ).url()
    html = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN"},
                        timeout=30).text
    labels = [l for l in re.findall(r'aria-label="([^"]{40,600})"', html) if "选择航班" in l]
    flights, seen = [], set()
    for lb in labels:
        f = _label_to_flight(lb, dep_code, arr_code, date)
        if f and f["id"] not in seen:
            seen.add(f["id"])
            flights.append(f)
    lowest = min((f["price"] for f in flights), default=None)
    return {"login_needed": False, "flights": flights, "lowestPrice": lowest,
            "count": len(flights)}
