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
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
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
            userAgentString = "$userAgentString JACC-Android/1.12"
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
                webView.settings.cacheMode = WebSettings.LOAD_DEFAULT
                if (!serviceWorkerResetAttempted) {
                    serviceWorkerResetAttempted = true
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
        val connectTimeout = timeoutMs.coerceIn(1_000, 30_000)
        val readTimeout = timeoutMs.coerceIn(1_000, 120_000)
        val requestBody = body.toByteArray(StandardCharsets.UTF_8)

        while (redirects++ < 4) {
            val url = URL(currentUrl)
            val host = url.host.lowercase()
            if (url.protocol.lowercase() != "https" ||
                host != "script.google.com" && host != "script.googleusercontent.com"
            ) {
                throw IOException("native_transport_host_blocked")
            }

            val connection = (url.openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                useCaches = false
                doInput = true
                requestMethod = method
                this.connectTimeout = connectTimeout
                this.readTimeout = readTimeout
                setRequestProperty("Accept", "application/json")
                setRequestProperty("Accept-Encoding", "identity")
                setRequestProperty("Cache-Control", "no-cache")
                setRequestProperty("Connection", "close")
                setRequestProperty("User-Agent", "JACC-Android/1.12")
                if (method == "POST") {
                    doOutput = true
                    setFixedLengthStreamingMode(requestBody.size)
                    setRequestProperty("Content-Type", "text/plain; charset=UTF-8")
                }
            }

            try {
                connection.connect()
                if (method == "POST") {
                    connection.outputStream.use { stream ->
                        stream.write(requestBody)
                        stream.flush()
                    }
                }

                val status = connection.responseCode
                if (status in 300..399) {
                    val location = connection.getHeaderField("Location")
                        ?: throw IOException("native_transport_redirect_missing")
                    currentUrl = URL(url, location).toString()
                    method = "GET"
                    continue
                }

                val stream = if (status >= 400) connection.errorStream else connection.inputStream
                val responseBody = stream?.bufferedReader(StandardCharsets.UTF_8)?.use { it.readText() } ?: ""
                return NativeHttpResult(status, responseBody)
            } finally {
                connection.disconnect()
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
            "https://kyawmintun08.github.io/Japan-Auction-Car-Checker/?app=flutter&jacc_app=1&build=2026.08.21.2&recovery=2026.08.21.1&native=1.12&shell=faststart-native-transport-diagnostics-v11&transport=native-redirect-v5&nav=20260821-4"
    }
}
