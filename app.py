# -*- coding: utf-8 -*-
"""CheapestFlight PC 版后端（F1）。

启动一个本地 Flask 服务：托管前端、提供搜索 API；数据源为「登录态 Chrome」（sources/fliggy.py）。
运行：python app.py  → 自动开浏览器到 http://127.0.0.1:8770
"""
import os
import threading
import webbrowser

from flask import Flask, jsonify, request, send_from_directory

import cities as cities_mod
from sources.fliggy import get_browser

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PORT = int(os.environ.get("CHEAPESTFLIGHT_PORT", "8770"))

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(WEB_DIR, path)


@app.route("/api/cities")
def api_cities():
    return jsonify(cities_mod.city_list())


@app.route("/api/login-status")
def api_login_status():
    try:
        return jsonify(get_browser().check_login())
    except Exception as e:
        return jsonify({"logged_in": False, "error": str(e)}), 500


@app.route("/api/login", methods=["POST"])
def api_login():
    try:
        get_browser().open_login()
        return jsonify({"ok": True, "msg": "已在浏览器窗口打开淘宝登录页，请扫码/密码登录后再搜索"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/search")
def api_search():
    dep_raw = (request.args.get("dep") or "").strip()
    arr_raw = (request.args.get("arr") or "").strip()
    date = (request.args.get("date") or "").strip()
    if not dep_raw or not arr_raw or not date:
        return jsonify({"error": "缺少出发地/到达地/日期"}), 400
    dep = cities_mod.resolve(dep_raw)
    arr = cities_mod.resolve(arr_raw)
    if not dep:
        return jsonify({"error": f"无法识别出发地：{dep_raw}（可输入城市名或三字码）"}), 400
    if not arr:
        return jsonify({"error": f"无法识别到达地：{arr_raw}（可输入城市名或三字码）"}), 400
    dep_code, dep_name, dep_intl = dep
    arr_code, arr_name, arr_intl = arr
    intl = dep_intl or arr_intl  # 任一端为国际/港澳台 → 走国际列表页
    try:
        res = get_browser().search(dep_code, arr_code, date, intl, dep_name, arr_name)
    except Exception as e:
        return jsonify({"error": f"搜索失败：{e}"}), 500
    res["query"] = {
        "dep": {"code": dep_code, "name": dep_name},
        "arr": {"code": arr_code, "name": arr_name},
        "date": date, "intl": intl,
    }
    return jsonify(res)


def _open_browser():
    webbrowser.open(f"http://127.0.0.1:{PORT}")


def main():
    threading.Timer(1.2, _open_browser).start()
    print(f"CheapestFlight 运行中 → http://127.0.0.1:{PORT}")
    app.run(host="127.0.0.1", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
