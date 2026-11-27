package com.voxpc.remote.net

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

/**
 * Связь «телефон вне дома» -> «телефон-ретранслятор дома» через ntfy.sh.
 * Канал — секретный ключ, который оба телефона получают от VoxPC при «Найти ПК».
 */
object WakeRelay {
    const val NTFY = "https://ntfy.sh"

    fun topic(remoteId: String) = "$remoteId-wake"
    fun ackTopic(remoteId: String) = "$remoteId-wake-ack"

    fun post(topic: String, body: String) {
        val c = URL("$NTFY/$topic").openConnection() as HttpURLConnection
        try {
            c.requestMethod = "POST"
            c.connectTimeout = 8000
            c.readTimeout = 8000
            c.doOutput = true
            c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            require(c.responseCode in 200..299) { "ntfy ответил кодом ${c.responseCode}" }
        } finally {
            c.disconnect()
        }
    }

    /** Отправляет команду и ждёт ответ ретранслятора. onAck вызывается для каждого ответа. */
    suspend fun wake(remoteId: String, token: String, onAck: (String) -> Unit): Result<Boolean> =
        withContext(Dispatchers.IO) {
            runCatching {
                require(remoteId.isNotBlank()) { "Сначала нажмите «Найти ПК», находясь дома" }
                val id = UUID.randomUUID().toString().take(8)
                val since = System.currentTimeMillis() / 1000 - 2
                post(topic(remoteId), JSONObject().put("cmd", "wake").put("token", token).put("id", id).toString())
                // ждём ответы: «sent» — пакет отправлен, «online» — ПК включился
                var gotSent = false
                val seen = mutableSetOf<String>()
                val deadline = System.currentTimeMillis() + 100_000
                while (System.currentTimeMillis() < deadline) {
                    delay(if (gotSent) 4000 else 2000)
                    val c = URL("$NTFY/${ackTopic(remoteId)}/json?poll=1&since=$since").openConnection() as HttpURLConnection
                    c.connectTimeout = 8000
                    c.readTimeout = 10000
                    val text = try {
                        c.inputStream.bufferedReader().use { it.readText() }
                    } catch (e: Exception) {
                        ""
                    } finally {
                        c.disconnect()
                    }
                    for (line in text.lines().filter { it.isNotBlank() }) {
                        val msg = runCatching { JSONObject(JSONObject(line).optString("message")) }.getOrNull() ?: continue
                        if (msg.optString("id") != id) continue
                        val status = msg.optString("status")
                        if (!seen.add(status)) continue
                        onAck(status)
                        if (status == "sent") gotSent = true
                        if (status == "online" || status == "denied" || status == "error") return@runCatching true
                    }
                    if (!gotSent && System.currentTimeMillis() > deadline - 85_000) {
                        return@runCatching false   // за 15 с ретранслятор не ответил
                    }
                }
                gotSent
            }
        }
}
