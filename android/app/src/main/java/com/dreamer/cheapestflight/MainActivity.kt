package com.dreamer.cheapestflight

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.webkit.WebSettingsCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * CheapestFlight 骨架（SPEC §3.3 落地路径）。
 *
 * 一个真实 WebView 加载飞猪官方机票页——因为是真实 WebView 而非自动化浏览器，
 * 行为等同用户的真人 Chrome，能正常渲染、正常触发数据网关调用。页面脚本执行前
 * 注入 fetch/XHR 钩子，拦截飞猪机票接口（listingsearch / serverless 网关）的
 * 响应 JSON，落盘到 app 专属外部目录，供「分享」发出以确定卡片字段结构。
 *
 * 骨架阶段不含任何本地服务/Python——纯拦截取样。
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var countLabel: TextView
    private var captureCount = 0

    companion object {
        // 应用内启动页（assets），列出飞猪机票入口
        const val HOME = "file:///android_asset/home.html"
        // 移动端 Chrome UA：拿到移动版 H5 机票页（其数据走我们要拦截的网关）
        const val UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 " +
                "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

        // 在页面自身脚本执行前注入：包装 fetch 与 XMLHttpRequest，命中航班接口即上报原文
        const val HOOK_JS = """
(function(){
  if (window.__cfHookInstalled) return; window.__cfHookInstalled = true;
  function want(u){ try{ u = String(u||''); }catch(e){ return false; }
    return u.indexOf('listingsearch') >= 0
        || u.indexOf('interflight') >= 0
        || u.indexOf('serverless.api.gateway') >= 0
        || u.indexOf('flight.calendar') >= 0; }
  function report(u, body){ try{ if(window.CF && body) window.CF.onCapture(String(u), String(body)); }catch(e){} }
  // fetch
  if (window.fetch){
    var of = window.fetch;
    window.fetch = function(){
      var args = arguments;
      var u = (args[0] && args[0].url) ? args[0].url : args[0];
      return of.apply(this, args).then(function(resp){
        try { if (want(u)) resp.clone().text().then(function(t){ report(u, t); }); } catch(e){}
        return resp;
      });
    };
  }
  // XMLHttpRequest
  var oOpen = XMLHttpRequest.prototype.open;
  var oSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m, u){ this.__cfUrl = u; return oOpen.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function(){
    var self = this;
    this.addEventListener('load', function(){
      try { if (want(self.__cfUrl)) report(self.__cfUrl, self.responseText); } catch(e){}
    });
    return oSend.apply(this, arguments);
  };
})();
"""
    }

    private fun dp(v: Int): Int = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }

        // ---- 顶栏：标题 + 已抓取计数 + 首页 + 分享 ----
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(Color.parseColor("#1E88E5"))
            setPadding(dp(14), dp(8), dp(8), dp(8))
        }
        countLabel = TextView(this).apply {
            text = "已抓取 0"
            setTextColor(Color.WHITE)
            textSize = 15f
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }
        bar.addView(countLabel)
        bar.addView(Button(this).apply {
            text = "首页"
            setOnClickListener { webView.loadUrl(HOME) }
        })
        bar.addView(Button(this).apply {
            text = "分享"
            setOnClickListener { shareLatestCapture() }
        })
        root.addView(bar, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))

        // ---- WebView ----
        webView = WebView(this)
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            userAgentString = UA
            useWideViewPort = true
            loadWithOverviewMode = true
            mediaPlaybackRequiresUserGesture = false
        }
        // 屏蔽 X-Requested-With 头 → 站点识别不出是嵌入式 WebView（登录/风控更顺）
        if (WebViewFeature.isFeatureSupported(WebViewFeature.REQUESTED_WITH_HEADER_ALLOW_LIST)) {
            WebSettingsCompat.setRequestedWithHeaderOriginAllowList(webView.settings, emptySet())
        }
        // 页面脚本执行前注入拦截钩子（比 onPageStarted 更早、更可靠）
        if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            try {
                WebViewCompat.addDocumentStartJavaScript(webView, HOOK_JS, setOf("*"))
            } catch (e: Exception) { /* 回退到 onPageStarted 注入 */ }
        }

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.addJavascriptInterface(CaptureBridge(), "CF")

        // JS 弹窗（alert/confirm）与登录二维码需要默认 WebChromeClient，否则被静默吞掉
        webView.webChromeClient = WebChromeClient()

        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView, url: String?, favicon: android.graphics.Bitmap?) {
                super.onPageStarted(view, url, favicon)
                // DOCUMENT_START_SCRIPT 不支持时的回退注入
                if (!WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
                    view.evaluateJavascript(HOOK_JS, null)
                }
            }

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url?.toString() ?: return false
                // http/https 与本地 asset 留在 WebView 内
                if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("file://")) {
                    return false
                }
                // 拦掉 tbopen:// taobao:// tmall:// alipays:// intent:// 等唤起原生 App 的深链，
                // 强制留在 WebView（否则会跳出去打开淘宝/支付宝 App）
                return true
            }
        }
        root.addView(webView, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))

        setContentView(root)
        webView.loadUrl(HOME)
    }

    /** JS → 原生：收到一条命中的航班接口响应 */
    private inner class CaptureBridge {
        @JavascriptInterface
        fun onCapture(url: String, body: String) {
            // 过滤明显过小的（非数据）响应，减少噪声
            if (body.length < 200) return
            Thread {
                try {
                    val dir = File(getExternalFilesDir(null), "captures").apply { mkdirs() }
                    val ts = SimpleDateFormat("yyyyMMdd_HHmmss_SSS", Locale.US).format(Date())
                    val tag = when {
                        url.contains("listingsearch") -> "listingsearch"
                        url.contains("serverless.api.gateway") -> "gateway"
                        url.contains("calendar") -> "calendar"
                        else -> "flight"
                    }
                    val f = File(dir, "${tag}_$ts.json")
                    // 存一个带元信息的信封，便于回溯是哪个接口
                    f.writeText("{\"url\":${jsonStr(url)},\"capturedAt\":\"$ts\",\"body\":${jsonStr(body)}}")
                    runOnUiThread {
                        captureCount++
                        countLabel.text = "已抓取 $captureCount"
                        Toast.makeText(this@MainActivity,
                            "抓到 $tag 响应 ✓（$captureCount）", Toast.LENGTH_SHORT).show()
                    }
                } catch (e: Exception) {
                    runOnUiThread {
                        Toast.makeText(this@MainActivity, "保存失败：${e.message}",
                            Toast.LENGTH_SHORT).show()
                    }
                }
            }.start()
        }
    }

    /** 把最近一次抓取的 JSON 通过系统分享发出去 */
    private fun shareLatestCapture() {
        val dir = File(getExternalFilesDir(null), "captures")
        val files = dir.listFiles()?.filter { it.isFile }?.sortedByDescending { it.lastModified() }
        if (files.isNullOrEmpty()) {
            Toast.makeText(this, "还没有抓取到数据，先登录并搜索一次机票", Toast.LENGTH_LONG).show()
            return
        }
        val latest = files.first()
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", latest)
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "application/json"
            putExtra(Intent.EXTRA_STREAM, uri)
            putExtra(Intent.EXTRA_SUBJECT, latest.name)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(Intent.createChooser(send, "分享抓取的航班数据（共 ${files.size} 份）"))
    }

    /** 极简 JSON 字符串转义（够用于把任意文本安全嵌入信封） */
    private fun jsonStr(s: String): String {
        val sb = StringBuilder("\"")
        for (c in s) {
            when (c) {
                '\\' -> sb.append("\\\\")
                '"' -> sb.append("\\\"")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                else -> if (c < ' ') sb.append(String.format("\\u%04x", c.code)) else sb.append(c)
            }
        }
        return sb.append("\"").toString()
    }

    override fun onBackPressed() {
        if (this::webView.isInitialized && webView.canGoBack()) webView.goBack()
        else super.onBackPressed()
    }
}
