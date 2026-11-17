package com.voxpc.remote.net

import com.voxpc.remote.data.Prefs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class PingResult(val online: Boolean, val authorized: Boolean, val name: String, val remote: Boolean = false)
data class PcApp(val name: String, val icon: String)
data class CommandResult(val ok: Boolean, val message: String)

/** HTTP-клиент к VoxPC: дома — напрямую по Wi-Fi, вне дома — через туннель VoxPC. */
class PcClient(private val prefs: Prefs) {

    @Volatile
    var remote = false
        private set
    private var lastRelayCheck = 0L

    private fun base(): String =
        if (remote && prefs.remoteUrl.isNotBlank()) prefs.remoteUrl.trimEnd('/')
        else "http://${prefs.host}:${prefs.port}"

    private fun request(method: String, path: String, body: JSONObject? = null, timeout: Int = 5000,
                        baseUrl: String = base()): Pair<Int, ByteArray> {
        val conn = URL(baseUrl + path).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            val https = baseUrl.startsWith("https")
            conn.connectTimeout = if (https) maxOf(timeout, 6000) else timeout
            conn.readTimeout = if (https) maxOf(timeout, 8000) else timeout
            conn.setRequestProperty("X-Token", prefs.token)
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val bytes = stream?.use { it.readBytes() } ?: ByteArray(0)
            return code to bytes
        } finally {
            conn.disconnect()
        }
    }

    private fun pingAt(baseUrl: String, timeout: Int): PingResult? = try {
        val (code, bytes) = request("GET", "/api/ping", timeout = timeout, baseUrl = baseUrl)
        val j = JSONObject(String(bytes, Charsets.UTF_8))
        PingResult(code == 200, j.optBoolean("auth"), j.optString("name"))
    } catch (e: Exception) {
        null
    }

    /** Проверяет связь: сначала домашняя сеть, затем интернет-адрес ПК. */
    suspend fun ping(): PingResult = withContext(Dispatchers.IO) {
        if (prefs.host.isNotBlank()) {
            val home = pingAt("http://${prefs.host}:${prefs.port}", 1500)
            if (home != null) {
                remote = false
                return@withContext home
            }
        }
        if (prefs.remoteId.isBlank()) {
            remote = false
            return@withContext PingResult(false, false, "")
        }
        if (prefs.remoteUrl.isNotBlank()) {
            val r = pingAt(prefs.remoteUrl.trimEnd('/'), 6000)
            if (r != null) {
                remote = true
                return@withContext r.copy(remote = true)
            }
        }
        // адрес туннеля мог смениться после перезагрузки ПК — узнаём новый
        val now = System.currentTimeMillis()
        if (now - lastRelayCheck > 30_000) {
            lastRelayCheck = now
            val fresh = Relay.fetchUrl(prefs.remoteId)
            if (fresh != null && fresh != prefs.remoteUrl) {
                prefs.remoteUrl = fresh
                val r = pingAt(fresh, 6000)
                if (r != null) {
                    remote = true
                    return@withContext r.copy(remote = true)
                }
            }
        }
        remote = false
        PingResult(false, false, "")
    }

    suspend fun apps(): List<PcApp> = withContext(Dispatchers.IO) {
        try {
            val (code, bytes) = request("GET", "/api/apps")
            if (code != 200) return@withContext emptyList()
            val arr = JSONArray(String(bytes, Charsets.UTF_8))
            List(arr.length()) { i ->
                val o = arr.getJSONObject(i)
                PcApp(o.optString("name"), o.optString("icon", "🧩"))
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    /** Снимок экрана ПК в JPEG. */
    suspend fun screen(maxSide: Int, quality: Int): ByteArray? = withContext(Dispatchers.IO) {
        try {
            val (code, bytes) = request("GET", "/api/screen?max=$maxSide&q=$quality", timeout = 8000)
            if (code == 200 && bytes.size > 100) bytes else null
        } catch (e: Exception) {
            null
        }
    }

    // Claude может думать до минуты
    suspend fun command(text: String) = post("/api/command", JSONObject().put("text", text), timeout = 90000)

    suspend fun action(action: String, app: String? = null): CommandResult {
        val body = JSONObject().put("action", action)
        if (app != null) body.put("app", app)
        return post("/api/action", body)
    }

    private suspend fun post(path: String, body: JSONObject, timeout: Int = 8000): CommandResult =
        withContext(Dispatchers.IO) {
            if (prefs.host.isBlank() && prefs.remoteUrl.isBlank())
                return@withContext CommandResult(false, "Сначала подключите ПК в настройках")
            try {
                val (code, bytes) = request("POST", path, body, timeout)
                if (code == 401) return@withContext CommandResult(false, "Неверный код доступа")
                val j = JSONObject(String(bytes, Charsets.UTF_8))
                CommandResult(j.optBoolean("ok"), j.optString("message"))
            } catch (e: Exception) {
                CommandResult(false, "ПК не отвечает. Он включён и VoxPC запущен?")
            }
        }
}
