# -*- coding: utf-8 -*-
"""把飞猪 listingsearch 响应解析为归一化航班对象（SPEC §8）。

只取 items 里 itemType 为 FLIGHT_DIRECT / FLIGHT_TRANSFER 的条目，
其余（TOP_MULTI_TAB / ECONOMY_RECOMMEND / TITLE / LOW_PRICE_MONITOR）是 UI 装饰，跳过。
"""
from datetime import datetime

FLIGHT_ITEM_TYPES = ("FLIGHT_DIRECT", "FLIGHT_TRANSFER")


def _dt(s):
    """'2026-07-16 22:05:00' -> datetime；失败返回 None。"""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M")
        except ValueError:
            return None


def _cross_days(dep, arr):
    """按日期部分算跨天数（到达日 - 出发日）。"""
    d1, d2 = _dt(dep), _dt(arr)
    if not d1 or not d2:
        return 0
    return (d2.date() - d1.date()).days


def _price_yuan(card):
    """飞猪头条展示价＝惠后价（元）。优先 trackInfo（已是元），回退 priceInfo（分）。"""
    tk = card.get("trackInfo") or {}
    if tk.get("afterPromotionPrice") is not None:
        return tk["afterPromotionPrice"]
    if tk.get("salePrice") is not None:
        return tk["salePrice"]
    pi = card.get("priceInfo") or {}
    v = pi.get("afterPromotionPrice") or pi.get("adultPrice")
    return round(v / 100) if v is not None else None


def _seg(s):
    return {
        "flightNo": s.get("marketingFlightNo"),
        "airlineName": s.get("marketingAirlineName"),
        "airlineCode": s.get("marketingAirlineCode"),
        "airlineIcon": _icon(s.get("marketingAirlineIconUrl")),
        "planeType": s.get("planeType"),
        "codeShare": s.get("codeShare", False),
        "depTime": s.get("depTime"),
        "arrTime": s.get("arrTime"),
        "durationMin": s.get("duration"),
        "dep": {
            "cityName": s.get("depCityName"), "cityCode": s.get("depCityCode"),
            "airportName": s.get("depAirportName"), "airportCode": s.get("depAirportCode"),
            "term": s.get("depTerm") or "",
        },
        "arr": {
            "cityName": s.get("arrCityName"), "cityCode": s.get("arrCityCode"),
            "airportName": s.get("arrAirportName"), "airportCode": s.get("arrAirportCode"),
            "term": s.get("arrTerm") or "",
        },
    }


def _icon(url):
    if not url:
        return None
    return ("https:" + url) if url.startswith("//") else url


def _card_to_flight(card, item_type):
    fi = (card.get("flightInfos") or [{}])[0]
    segs = [_seg(s) for s in (fi.get("flightSegments") or [])]
    tk = card.get("trackInfo") or {}
    dep_time = fi.get("depTime")
    arr_time = fi.get("arrTime")
    is_transfer = item_type == "FLIGHT_TRANSFER" or (fi.get("transferCount") or 0) > 0

    # 中转地：各航段之间的落地城市（除最后一段外每段的到达城市）
    stops = []
    if is_transfer and len(segs) >= 2:
        for s in segs[:-1]:
            stops.append({
                "cityName": s["arr"]["cityName"],
                "airportName": s["arr"]["airportName"],
                "airportCode": s["arr"]["airportCode"],
            })

    airlines = []
    for s in segs:
        if s["airlineName"] and s["airlineName"] not in airlines:
            airlines.append(s["airlineName"])

    flight_nos = tk.get("flightNos") or "_".join(s["flightNo"] for s in segs if s["flightNo"])

    return {
        "id": f"{tk.get('depDate','')}_{flight_nos}_{fi.get('depAirportCode','')}_{fi.get('arrAirportCode','')}",
        "type": "transfer" if is_transfer else "direct",
        "depDate": tk.get("depDate"),
        "depTime": dep_time,
        "arrTime": arr_time,
        "crossDays": _cross_days(dep_time, arr_time),
        "durationMin": fi.get("duration"),
        "transferCount": fi.get("transferCount") or 0,
        "dep": {
            "cityName": segs[0]["dep"]["cityName"] if segs else None,
            "cityCode": tk.get("depCityCode"),
            "airportName": fi.get("depAirportName"),
            "airportShortName": fi.get("depAirportShortName"),
            "airportCode": fi.get("depAirportCode"),
            "term": fi.get("depTerm") or "",
        },
        "arr": {
            "cityName": segs[-1]["arr"]["cityName"] if segs else None,
            "cityCode": tk.get("arrCityCode"),
            "airportName": fi.get("arrAirportName"),
            "airportShortName": fi.get("arrAirportShortName"),
            "airportCode": fi.get("arrAirportCode"),
            "term": fi.get("arrTerm") or "",
        },
        "stops": stops,
        "segments": segs,
        "airlines": airlines,
        "flightNos": flight_nos,
        "price": _price_yuan(card),
        "salePrice": tk.get("salePrice"),
        "tax": tk.get("tax"),
    }


def parse_listingsearch(data):
    """入参为 listingsearch 响应体的 data 字段。返回归一化航班列表。"""
    flights = []
    if not isinstance(data, dict):
        return flights
    for item in data.get("items") or []:
        it = item.get("itemType")
        if it not in FLIGHT_ITEM_TYPES:
            continue
        for card in item.get("data") or []:
            if not isinstance(card, dict) or "flightInfos" not in card:
                continue
            try:
                flights.append(_card_to_flight(card, it))
            except Exception:
                continue
    return flights


def lowest_price(data):
    return (data or {}).get("lowestPrice") if isinstance(data, dict) else None
