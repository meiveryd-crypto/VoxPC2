package com.voxpc.remote.net

import com.voxpc.remote.data.Prefs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class PingResult(val online: Boolean, val authorized: Boolean, val name: String)
data class PcApp(val name: String, val icon: String)
data class CommandResult(val ok: Boolean, val message: String)

/** HTTP-клиент к программе VoxPC на компьютере. */
class PcClient(private val prefs: Prefs) {

    private fun request(method: String, path: String, body: JSONObject? = null, timeout: Int = 5000): Pair<Int, String> {
        val conn = URL("http://${prefs.host}:${prefs.port}$path").openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = timeout
            conn.readTimeout = timeout
            conn.setRequestProperty("X-Token", prefs.token)
            conn.setRequestProperty("Accept", "application/json")
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            return code to text
        } finally {
            conn.disconnect()
        }
    }

    suspend fun ping(): PingResult = withContext(Dispatchers.IO) {
        if (prefs.host.isBlank()) return@withContext PingResult(false, false, "")
        try {
            val (code, text) = request("GET", "/api/ping", timeout = 2000)
            val j = JSONObject(text)
            PingResult(code == 200, j.optBoolean("auth"), j.optString("name"))
        } catch (e: Exception) {
            PingResult(false, false, "")
        }
    }

    suspend fun apps(): List<PcApp> = withContext(Dispatchers.IO) {
        try {
            val (code, text) = request("GET", "/api/apps")
            if (code != 200) return@withContext emptyList()
            val arr = JSONArray(text)
            List(arr.length()) { i ->
                val o = arr.getJSONObject(i)
                PcApp(o.optString("name"), o.optString("icon", "🧩"))
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    // Claude может думать до минуты
    suspend fun command(text: String) = post("/api/command", JSONObject().put("text", text), timeout = 90000)

    suspend fun action(action: String, app: String? = null): CommandResult {
        val body = JSONObject().put("action", action)
        if (app != null) body.put("app", app)
        return post("/api/action", body)
    }

    private suspend fun post(path: String, body: JSONObject, timeout: Int = 8000): CommandResult = withContext(Dispatchers.IO) {
        if (prefs.host.isBlank()) return@withContext CommandResult(false, "Сначала подключите ПК в настройках")
        try {
            val (code, text) = request("POST", path, body, timeout)
            if (code == 401) return@withContext CommandResult(false, "Неверный код доступа")
            val j = JSONObject(text)
            CommandResult(j.optBoolean("ok"), j.optString("message"))
        } catch (e: Exception) {
            CommandResult(false, "ПК не отвечает. Он включён и VoxPC запущен?")
        }
    }
}
