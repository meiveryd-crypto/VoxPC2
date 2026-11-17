package com.voxpc.remote.net

import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.CookieHandler
import java.net.CookieManager
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** Узнаёт текущий адрес туннеля VoxPC: ПК публикует его в секретном канале ntfy.sh. */
object Relay {
    suspend fun fetchUrl(remoteId: String): String? = withContext(Dispatchers.IO) {
        if (remoteId.isBlank()) return@withContext null
        try {
            val conn = URL("https://ntfy.sh/$remoteId/json?poll=1&since=24h").openConnection() as HttpURLConnection
            conn.connectTimeout = 6000
            conn.readTimeout = 8000
            val text = conn.inputStream.bufferedReader().use { it.readText() }
            conn.disconnect()
            text.lines().filter { it.isNotBlank() }.mapNotNull {
                runCatching { JSONObject(it).optString("message") }.getOrNull()
            }.lastOrNull { it.startsWith("https://") && it.length < 200 }
        } catch (e: Exception) {
            null
        }
    }
}

/** Включение ПК через роутер Keenetic (функция «Разбудить» по REST API, работает и через KeenDNS). */
object Keenetic {
    init {
        if (CookieHandler.getDefault() == null) CookieHandler.setDefault(CookieManager())
    }

    private fun hex(algo: String, s: String): String =
        MessageDigest.getInstance(algo).digest(s.toByteArray()).joinToString("") { "%02x".format(it) }

    private fun open(url: String, method: String, basic: String?, body: String? = null): HttpURLConnection {
        val c = URL(url).openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = 8000
        c.readTimeout = 10000
        if (basic != null) c.setRequestProperty("Authorization", "Basic $basic")
        if (body != null) {
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json")
            c.outputStream.use { it.write(body.toByteArray()) }
        }
        return c
    }

    suspend fun wake(routerUrl: String, login: String, password: String, mac: String): Result<Unit> =
        withContext(Dispatchers.IO) {
            runCatching {
                var base = routerUrl.trim().trimEnd('/')
                require(base.isNotBlank()) { "Укажите адрес роутера Keenetic" }
                if (!base.startsWith("http")) base = "https://$base"
                val basic = if (login.isNotBlank())
                    Base64.encodeToString("$login:$password".toByteArray(), Base64.NO_WRAP) else null
                // 1) родная авторизация Keenetic (challenge), если доступна
                val probe = open("$base/auth", "GET", basic)
                val code = probe.responseCode
                val challenge = probe.getHeaderField("X-NDM-Challenge")
                val realm = probe.getHeaderField("X-NDM-Realm")
                probe.disconnect()
                if (code == 401 && challenge != null && realm != null) {
                    val pass = hex("SHA-256", challenge + hex("MD5", "$login:$realm:$password"))
                    val auth = open("$base/auth", "POST", basic,
                        JSONObject().put("login", login).put("password", pass).toString())
                    val ok = auth.responseCode
                    auth.disconnect()
                    require(ok == 200) { "Роутер не принял логин или пароль" }
                } else {
                    require(code == 200 || code == 401) { "Роутер ответил кодом $code" }
                }
                // 2) команда «разбудить»
                val m = mac.filter { it.isLetterOrDigit() }.lowercase().chunked(2).joinToString(":")
                require(m.length == 17) { "Не указан MAC-адрес ПК" }
                val wake = open("$base/rci/ip/hotspot/wake", "POST", basic, JSONObject().put("mac", m).toString())
                val wc = wake.responseCode
                wake.disconnect()
                require(wc == 200) {
                    if (wc == 401) "Роутер не принял логин или пароль" else "Роутер ответил кодом $wc"
                }
            }
        }
}
