package com.kyawmintun.jacc

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.util.Base64
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.WebSettings
import android.webkit.ValueCallback
import android.webkit.JavascriptInterface
import android.security.keystore.KeyGenParameterSpec
import java.io.IOException
import java.net.URL
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.MediaType.Companion.toMediaType
import org.json.JSONObject
import android.security.keystore.KeyProperties
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import android.widget.Button
import android.widget.ProgressBar
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity

private class RememberLoginBridge(context: Context) {

    companion object {
        private const val PREFS_NAME = "jacc_remember_login_v1"
        private const val DATA_KEY = "ciphertext"
        private const val IV_KEY = "iv"
        private const val KEY_ALIAS = "jacc_remember_login_aes_v1"
        private const val KEYSTORE = "AndroidKeyStore"
    }

    private val preferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    @JavascriptInterface
    fun isSupported(): Boolean = runCatching {
        getOrCreateKey()
        true
    }.getOrDefault(false)

    @JavascriptInterface
    fun has(): Boolean = preferences.contains(DATA_KEY) && preferences.contains(IV_KEY)

    @JavascriptInterface
    fun save(password: String): Boolean = runCatching {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val ciphertext = cipher.doFinal(password.toByteArray(StandardCharsets.UTF_8))
        preferences.edit()
            .putString(DATA_KEY, Base64.encodeToString(ciphertext, Base64.NO_WRAP))
            .putString(IV_KEY, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .commit()
    }.getOrDefault(false)

    @JavascriptInterface
    fun read(): String = runCatching {
        if (!has()) return@runCatching ""
        val iv = Base64.decode(preferences.getString(IV_KEY, ""), Base64.DEFAULT)
        val ciphertext = Base64.decode(preferences.getString(DATA_KEY, ""), Base64.DEFAULT)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(128, iv))
        String(cipher.doFinal(ciphertext), StandardCharsets.UTF_8)
    }.getOrDefault("")

    @JavascriptInterface
    fun clear(): Boolean = runCatching {
        preferences.edit().clear().commit()
    }.getOrDefault(false)

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        if (keyStore.containsAlias(KEY_ALIAS)) {
            return keyStore.getKey(KEY_ALIAS, null) as SecretKey
        }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generator.generateKey()
    }
}

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var errorPanel: View
    private var filePathCallback: ValueCallback<Array<Uri>>? = null
    private var startupRecoveryAttempted = false
    private var startupPageFinished = false
    private var serviceWorkerResetAttempted = false
    private val startupHandler = Handler(Looper.getMainLooper())
    private val transportExecutor: ExecutorService = Executors.newCachedThreadPool()
    private val nativeHttpClient: OkHttpClient = OkHttpClient.Builder()
        .followRedirects(false)
        .followSslRedirects(false)
        .retryOnConnectionFailure(false)
        .connectTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
        .writeTimeout(120, java.util.concurrent.TimeUnit.SECONDS)
        .readTimeout(120, java.util.concurrent.TimeUnit.SECONDS)
        .build()

    private data class NativeHttpResult(val status: Int, val body: String)

    private val nativeTransportBridge = object {
        @JavascriptInterface
        fun postJson(requestId: String, url: String, body: String, timeoutMs: Int): Boolean {
            val id = requestId.trim()
            if (id.isEmpty()) return false
            transportExecutor.execute {
                val envelope = try {
                    val result = performNativePostJson(url, body, timeoutMs)
                    JSONObject()
                        .put("ok", true)
                        .put("status", result.status)
                        .put("body", result.body)
                        .toString()
                } catch (error: Exception) {
                    JSONObject()
                        .put("ok", false)
                        .put("status", 0)
                        .put("error", error.message ?: "native_transport_error")
                        .toString()
                }
                val encoded = Base64.encodeToString(
                    envelope.toByteArray(StandardCharsets.UTF_8),
                    Base64.NO_WRAP
                )
                val script = "window.__jaccNativeTransportResolve(${JSONObject.quote(id)},${JSONObject.quote(encoded)})"
                runOnUiThread {
                    if (!isFinishing && !isDestroyed) {
                        webView.evaluateJavascript(script, null)
                    }
                }
            }
            return true
        }
    }

    private val startupRecoveryRunnable = Runnable {
        if (!startupPageFinished && !startupRecoveryAttempted && !isFinishing) {
            startupRecoveryAttempted = true
            webView.stopLoading()
            webView.clearCache(true)
            webView.settings.cacheMode = WebSettings.LOAD_NO_CACHE
            webView.loadUrl(APP_URL)
        }
    }

    private val fileChooserLauncher = registerForActivityResult(
        ActivityResultContracts.OpenMultipleDocuments()
    ) { uris ->
        filePathCallback?.onReceiveValue(uris.takeIf { it.isNotEmpty() }?.toTypedArray())
        filePathCallback = null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webView)
        progressBar = findViewById(R.id.progressBar)
        errorPanel = findViewById(R.id.errorPanel)

        findViewById<Button>(R.id.retryButton).setOnClickListener {
            errorPanel.visibility = View.GONE
            webView.visibility = View.VISIBLE
            webView.reload()
        }

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            loadsImagesAutomatically = true
            useWideViewPort = true
            loadWithOverviewMode = true
            builtInZoomControls = false
            displayZoomControls = false
            allowFileAccess = false
            allowContentAccess = true
            userAgentString = "$userAgentString JACC-Android/1.14"
        }

        webView.addJavascriptInterface(RememberLoginBridge(this), "JACCRememberLogin")
        webView.addJavascriptInterface(nativeTransportBridge, "JACCNativeTransport")

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                progressBar.progress = newProgress
                progressBar.visibility = if (newProgress < 100) View.VISIBLE else View.GONE
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                this@MainActivity.filePathCallback?.onReceiveValue(null)
                this@MainActivity.filePathCallback = filePathCallback

                val acceptedTypes = fileChooserParams?.acceptTypes
                    ?.filter { it.isNotBlank() && it != "*/*" }
                    ?.toTypedArray()
                    ?.takeIf { it.isNotEmpty() }
                    ?: arrayOf("image/*")

                return try {
                    fileChooserLauncher.launch(acceptedTypes)
                    true
                } catch (_: Exception) {
                    this@MainActivity.filePathCallback?.onReceiveValue(null)
                    this@MainActivity.filePathCallback = null
                    false
                }
            }
        }

        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                errorPanel.visibility = View.GONE
                webView.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                startupPageFinished = true
                startupHandler.removeCallbacks(startupRecoveryRunnable)
                if (!serviceWorkerResetAttempted) {
                    serviceWorkerResetAttempted = true
                    webView.settings.cacheMode = WebSettings.LOAD_NO_CACHE
                    val targetUrl = JSONObject.quote(APP_URL)
                    webView.evaluateJavascript(
                        """
                        (async function(){
                          try {
                            if (navigator.serviceWorker && navigator.serviceWorker.getRegistrations) {
                              const registrations = await navigator.serviceWorker.getRegistrations();
                              await Promise.all(registrations.map(function(registration){ return registration.unregister(); }));
                            }
                            if (window.caches && caches.keys) {
                              const keys = await caches.keys();
                              await Promise.all(keys.map(function(key){ return caches.delete(key); }));
                            }
                          } catch (ignore) {}
                          location.replace($targetUrl);
                        })();
                        """.trimIndent(),
                        null
                    )
                } else {
                    webView.settings.cacheMode = WebSettings.LOAD_DEFAULT
                }
            }

            override fun shouldOverrideUrlLoading(
                view: WebView?,
                request: WebResourceRequest?
            ): Boolean {
                val uri = request?.url ?: return false
                return openExternalIfNeeded(uri)
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame == true) {
                    webView.visibility = View.GONE
                    errorPanel.visibility = View.VISIBLE
                    progressBar.visibility = View.GONE
                }
            }
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else finish()
            }
        })

        // Always navigate to the current web shell. Restoring a saved WebView
        // state can revive an older service-worker-controlled document and keep
        // the app on the pre-paging startup path. Cookies, localStorage,
        // encrypted remember-login data, and device/session storage are not
        // cleared by this fresh navigation.
        webView.clearCache(true)
        webView.settings.cacheMode = WebSettings.LOAD_NO_CACHE
        webView.loadUrl(APP_URL)
        startupHandler.postDelayed(startupRecoveryRunnable, 20000L)
    }

    private fun performNativePostJson(urlString: String, body: String, timeoutMs: Int): NativeHttpResult {
        var currentUrl = urlString
        var method = "POST"
        var redirects = 0
        val requestBody = body.toRequestBody("text/plain; charset=UTF-8".toMediaType())
        val requestClient = nativeHttpClient.newBuilder()
            .connectTimeout(timeoutMs.coerceIn(1_000, 30_000).toLong(), java.util.concurrent.TimeUnit.MILLISECONDS)
            .writeTimeout(timeoutMs.coerceIn(1_000, 120_000).toLong(), java.util.concurrent.TimeUnit.MILLISECONDS)
            .readTimeout(timeoutMs.coerceIn(1_000, 120_000).toLong(), java.util.concurrent.TimeUnit.MILLISECONDS)
            .build()

        while (redirects++ < 4) {
            val url = URL(currentUrl)
            val host = url.host.lowercase()
            if (url.protocol.lowercase() != "https" ||
                host != "script.google.com" && host != "script.googleusercontent.com"
            ) {
                throw IOException("native_transport_host_blocked")
            }

            val requestBuilder = Request.Builder()
                .url(url)
                .header("Accept", "application/json")
                .header("Accept-Encoding", "identity")
                .header("Cache-Control", "no-cache")
                .header("Connection", "close")
                .header("User-Agent", "JACC-Android/1.13")

            if (method == "POST") requestBuilder.post(requestBody)
            else requestBuilder.get()

            requestClient.newCall(requestBuilder.build()).execute().use { response ->
                val status = response.code
                if (status in 300..399) {
                    val location = response.header("Location")
                        ?: throw IOException("native_transport_redirect_missing")
                    currentUrl = URL(url, location).toString()
                    method = "GET"
                    return@use
                }

                return NativeHttpResult(status, response.body?.string() ?: "")
            }
        }

        throw IOException("native_transport_redirect_limit")
    }

    private fun openExternalIfNeeded(uri: Uri): Boolean {
        val scheme = uri.scheme?.lowercase()
        val host = uri.host?.lowercase()
        val isJaccSite = scheme == "https" && host == "kyawmintun08.github.io"

        if (isJaccSite) return false

        return try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
            true
        } catch (_: Exception) {
            false
        }
    }

    override fun onDestroy() {
        filePathCallback?.onReceiveValue(null)
        filePathCallback = null
        startupHandler.removeCallbacks(startupRecoveryRunnable)
        transportExecutor.shutdownNow()
        webView.apply {
            stopLoading()
            clearHistory()
            removeAllViews()
            destroy()
        }
        super.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        webView.saveState(outState)
        super.onSaveInstanceState(outState)
    }

    companion object {
        private const val APP_URL =
            "https://kyawmintun08.github.io/Japan-Auction-Car-Checker/?app=flutter&jacc_app=1&build=2026.08.21.3&recovery=2026.08.21.2&native=1.14&shell=renderer-isolation-v12&transport=native-okhttp-v1&nav=20260821-6"
    }
}
