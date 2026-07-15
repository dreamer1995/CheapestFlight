# -*- coding: utf-8 -*-
"""飞猪数据源：驱动一个持久化「登录态」Chrome，导航机票列表页并拦截 listingsearch 响应。

SPEC §3.3 修正后的路线：真实登录态浏览器抓取（PC 可行）。Playwright 的同步 API 不能跨线程，
因此所有浏览器操作都在一个专属 worker 线程里串行执行，Flask 请求经队列提交任务。
"""
import gzip
import json
import os
import queue
import threading
import time
import urllib.parse
import zlib

from playwright.sync_api import sync_playwright

from .parse import parse_listingsearch, lowest_price

DEFAULT_PROFILE = os.path.join(os.path.expanduser("~"), ".cheapestflight", "chrome_profile")
PROFILE_DIR = os.environ.get("CHEAPESTFLIGHT_PROFILE", DEFAULT_PROFILE)
CHROME_CHANNEL = os.environ.get("CHEAPESTFLIGHT_CHROME_CHANNEL", "chrome")

UA_MOBILE = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

# 列表页（移动 H5）：国内 rx-flight-eco，国际 rx-iflight-eco
LISTING_DOMESTIC = "https://market.m.taobao.com/app/trip/rx-flight-eco/pages/listing"
LISTING_INTL = "https://market.m.taobao.com/app/trip/rx-iflight-eco/pages/listing"
LOGIN_URL = "https://login.taobao.com/"


def _decode_body(resp):
    """稳健读取响应体文本：优先 text()，回退 gzip / zlib / brotli。"""
    try:
        return resp.text()
    except Exception:
        pass
    try:
        b = resp.body()
    except Exception:
        return None
    for dec in (lambda x: x.decode("utf-8"),
                lambda x: gzip.decompress(x).decode("utf-8"),
                lambda x: zlib.decompress(x).decode("utf-8"),
                lambda x: zlib.decompress(x, -zlib.MAX_WBITS).decode("utf-8")):
        try:
            return dec(b)
        except Exception:
            continue
    try:
        import brotli  # 可选依赖
        return brotli.decompress(b).decode("utf-8")
    except Exception:
        return None


class _Job:
    __slots__ = ("fn", "event", "result", "error")

    def __init__(self, fn):
        self.fn = fn
        self.event = threading.Event()
        self.result = None
        self.error = None


class FliggyBrowser:
    """单 worker 线程持有 Playwright 持久化浏览器上下文，串行处理任务。"""

    def __init__(self):
        self._q = queue.Queue()
        self._ctx = None
        self._pw = None
        self._ready = threading.Event()
        self._start_error = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ---- worker 线程主体 ----
    def _run(self):
        try:
            os.makedirs(PROFILE_DIR, exist_ok=True)
            self._pw = sync_playwright().start()
            self._ctx = self._pw.chromium.launch_persistent_context(
                PROFILE_DIR,
                channel=CHROME_CHANNEL,
                headless=False,
                viewport={"width": 414, "height": 896},
                is_mobile=True, has_touch=True,
                locale="zh-CN",
                user_agent=UA_MOBILE,
                args=["--disable-blink-features=AutomationControlled",
                      "--no-first-run", "--no-default-browser-check"],
            )
            self._ready.set()
        except Exception as e:  # 启动失败
            self._start_error = e
            self._ready.set()
            return
        while True:
            job = self._q.get()
            if job is None:
                break
            try:
                job.result = job.fn(self._ctx)
            except Exception as e:
                job.error = e
            finally:
                job.event.set()

    def _submit(self, fn, timeout=90):
        self._ready.wait()
        if self._start_error:
            raise RuntimeError(f"浏览器启动失败：{self._start_error}")
        job = _Job(fn)
        self._q.put(job)
        if not job.event.wait(timeout):
            raise TimeoutError("浏览器任务超时")
        if job.error:
            raise job.error
        return job.result

    # ---- 对外能力 ----
    def check_login(self):
        return self._submit(self._check_login, timeout=40)

    def open_login(self):
        return self._submit(self._open_login, timeout=40)

    def search(self, dep_code, arr_code, date, intl, dep_name="", arr_name=""):
        return self._submit(
            lambda ctx: self._search(ctx, dep_code, arr_code, date, intl, dep_name, arr_name),
            timeout=90)

    # ---- 具体实现（都在 worker 线程内执行）----
    def _a_page(self, ctx):
        return ctx.pages[0] if ctx.pages else ctx.new_page()

    def _check_login(self, ctx):
        pg = self._a_page(ctx)
        pg.goto("https://h5.m.taobao.com/mlapp/mytaobao.html", wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(1500)
        url = pg.url
        # 跳到 login 域名 → 未登录
        logged = "login" not in url
        try:
            txt = pg.inner_text("body")[:400]
            if "请登录" in txt or "亲，请登录" in txt:
                logged = False
        except Exception:
            pass
        return {"logged_in": logged}

    def _open_login(self, ctx):
        pg = self._a_page(ctx)
        pg.bring_to_front()
        pg.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        return {"opened": True}

    def _search(self, ctx, dep_code, arr_code, date, intl, dep_name, arr_name):
        base = LISTING_INTL if intl else LISTING_DOMESTIC
        params = {
            "depCityCode": dep_code, "arrCityCode": arr_code,
            "depDate": date, "tripType": "0",
            "depCityName": dep_name or dep_code, "arrCityName": arr_name or arr_code,
            "_ts": str(int(time.time() * 1000)),
        }
        url = base + "?" + urllib.parse.urlencode(params)

        captured = {"best": None, "best_items": -1, "login_needed": False, "raw_data": None}

        def on_resp(resp):
            u = resp.url
            if "listingsearch" not in u:
                # 顺带侦测登录跳转
                if "login.taobao.com" in u or "havanaone" in u:
                    captured["login_needed"] = True
                return
            txt = _decode_body(resp)
            if not txt:
                return
            try:
                body = json.loads(txt)
            except Exception:
                return
            ret = (body.get("ret") or [""])[0]
            if "FAIL_SYS_SESSION" in ret or "needLogin" in ret or "NEED_LOGIN" in ret:
                captured["login_needed"] = True
                return
            data = body.get("data") or {}
            items = data.get("items") or []
            if len(items) > captured["best_items"]:
                captured["best_items"] = len(items)
                captured["raw_data"] = data

        pg = self._a_page(ctx)
        pg.on("response", on_resp)
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=45000)
            deadline = time.time() + 40
            while time.time() < deadline:
                pg.wait_for_timeout(1200)
                data = captured["raw_data"]
                if data is not None:
                    # 有结果且不再需要续拉就停
                    if not data.get("needContinue") and parse_listingsearch(data):
                        break
                if captured["login_needed"]:
                    break
        finally:
            try:
                pg.remove_listener("response", on_resp)
            except Exception:
                pass

        if captured["login_needed"] and captured["raw_data"] is None:
            return {"login_needed": True, "flights": [], "lowestPrice": None}

        data = captured["raw_data"] or {}
        flights = parse_listingsearch(data)
        return {
            "login_needed": False,
            "flights": flights,
            "lowestPrice": lowest_price(data),
            "count": len(flights),
        }


# 进程内单例
_instance = None
_lock = threading.Lock()


def get_browser():
    global _instance
    with _lock:
        if _instance is None:
            _instance = FliggyBrowser()
        return _instance
