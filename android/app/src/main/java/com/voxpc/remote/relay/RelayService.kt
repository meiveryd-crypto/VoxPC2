package com.voxpc.remote.relay

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.voxpc.remote.MainActivity
import com.voxpc.remote.R
import com.voxpc.remote.data.Prefs
import com.voxpc.remote.net.WakeOnLan
import com.voxpc.remote.net.WakeRelay
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Режим «телефон-ретранслятор»: телефон лежит дома в Wi-Fi, слушает секретный канал ntfy.sh
 * и по команде с вашего телефона отправляет «магический пакет» Wake-on-LAN в домашней сети.
 */
class RelayService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var wifiLock: WifiManager.WifiLock? = null
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL, "Ретранслятор VoxPC", NotificationManager.IMPORTANCE_LOW)
        )
        ServiceCompat.startForeground(
            this, NOTIF_ID, notification("Жду команду включения ПК"),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
        )
        val wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        @Suppress("DEPRECATION")
        wifiLock = wifi.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "voxpc:relay").apply { acquire() }
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "voxpc:relay").apply { acquire() }
        scope.launch { listen() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onDestroy() {
        scope.cancel()
        runCatching { wifiLock?.release() }
        runCatching { wakeLock?.release() }
        super.onDestroy()
    }

    private fun notification(text: String) = NotificationCompat.Builder(this, CHANNEL)
        .setSmallIcon(R.drawable.ic_launcher_foreground)
        .setContentTitle("VoxPC — ретранслятор")
        .setContentText(text)
        .setOngoing(true)
        .setContentIntent(
            PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        )
        .build()

    private fun update(text: String) {
        getSystemService(NotificationManager::class.java).notify(NOTIF_ID, notification(text))
    }

    private suspend fun listen() {
        val prefs = Prefs(this)
        var backoff = 2000L
        while (scope.isActive) {
            val topic = WakeRelay.topic(prefs.remoteId)
            if (prefs.remoteId.isBlank()) {
                update("Нажмите «Найти ПК» в приложении, чтобы связать ретранслятор с ПК")
                delay(30_000)
                continue
            }
            try {
                val since = System.currentTimeMillis() / 1000 - 5
                val c = URL("${WakeRelay.NTFY}/$topic/json?since=$since").openConnection() as HttpURLConnection
                c.connectTimeout = 15_000
                c.readTimeout = 120_000          // ntfy присылает keepalive каждые ~45 с
                c.inputStream.bufferedReader().useLines { lines ->
                    backoff = 2000L
                    for (line in lines) {
                        if (!scope.isActive) break
                        val event = runCatching { JSONObject(line) }.getOrNull() ?: continue
                        if (event.optString("event") != "message") continue
                        if (System.currentTimeMillis() / 1000 - event.optLong("time") > 120) continue
                        val msg = runCatching { JSONObject(event.optString("message")) }.getOrNull() ?: continue
                        if (msg.optString("cmd") == "wake") handleWake(prefs, msg)
                    }
                }
                c.disconnect()
            } catch (e: Exception) {
                update("Нет связи с интернетом, переподключаюсь…")
                delay(backoff)
                backoff = (backoff * 2).coerceAtMost(60_000)
            }
        }
    }

    private suspend fun handleWake(prefs: Prefs, msg: JSONObject) {
        val id = msg.optString("id")
        val ack = { status: String ->
            runCatching {
                WakeRelay.post(WakeRelay.ackTopic(prefs.remoteId), JSONObject().put("id", id).put("status", status).toString())
            }
        }
        if (msg.optString("token").uppercase() != prefs.token.uppercase() || prefs.token.isBlank()) {
            ack("denied")
            return
        }
        val r = WakeOnLan.send(prefs.mac, prefs.broadcast, prefs.wolPort, prefs.host)
        val time = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
        if (r.isFailure) {
            ack("error")
            update("Ошибка отправки сигнала ($time): ${r.exceptionOrNull()?.message}")
            return
        }
        ack("sent")
        update("Включил ПК в $time")
        prefs.relayLast = "Последняя команда: $time"
        // ждём, пока ПК загрузится, и сообщаем об этом
        repeat(30) {
            delay(4000)
            val online = runCatching {
                val c = URL("http://${prefs.host}:${prefs.port}/api/ping").openConnection() as HttpURLConnection
                c.connectTimeout = 2000
                c.readTimeout = 2000
                val ok = c.responseCode == 200
                c.disconnect()
                ok
            }.getOrDefault(false)
            if (online) {
                ack("online")
                update("ПК включился в ${SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())}")
                return
            }
        }
    }

    companion object {
        private const val CHANNEL = "relay"
        private const val NOTIF_ID = 47

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, RelayService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, RelayService::class.java))
        }
    }
}
