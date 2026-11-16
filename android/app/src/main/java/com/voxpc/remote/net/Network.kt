package com.voxpc.remote.net

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.SocketTimeoutException

/** Wake-on-LAN: «магический пакет» для включения ПК по сети. */
object WakeOnLan {
    suspend fun send(mac: String, broadcast: String, port: Int, pcHost: String): Result<Unit> =
        withContext(Dispatchers.IO) {
            runCatching {
                val hex = mac.filter { it.isLetterOrDigit() }
                require(hex.length == 12) { "Укажите MAC-адрес ПК в настройках" }
                val macBytes = hex.chunked(2).map { it.toInt(16).toByte() }
                val packet = ByteArray(6 + 16 * 6)
                for (i in 0 until 6) packet[i] = 0xFF.toByte()
                for (i in 0 until 16) for (j in 0 until 6) packet[6 + i * 6 + j] = macBytes[j]

                val targets = mutableSetOf<String>()
                if (broadcast.isNotBlank()) {
                    targets += broadcast
                } else {
                    targets += "255.255.255.255"
                    val parts = pcHost.split(".")
                    if (parts.size == 4 && parts.all { p -> p.toIntOrNull() != null }) {
                        targets += "${parts[0]}.${parts[1]}.${parts[2]}.255"
                    }
                }
                DatagramSocket().use { socket ->
                    socket.broadcast = true
                    repeat(3) {
                        for (t in targets) {
                            val addr = InetAddress.getByName(t)
                            for (p in setOf(port, 9, 7)) {
                                socket.send(DatagramPacket(packet, packet.size, addr, p))
                            }
                        }
                        Thread.sleep(80)
                    }
                }
            }
        }
}

data class FoundPc(val ip: String, val name: String, val port: Int, val mac: String)

/** Поиск ПК с запущенным VoxPC в локальной сети. */
object Discovery {
    private const val PORT = 47801

    suspend fun find(timeoutMs: Long = 2500): List<FoundPc> = withContext(Dispatchers.IO) {
        val found = mutableListOf<FoundPc>()
        try {
            DatagramSocket().use { socket ->
                socket.broadcast = true
                socket.soTimeout = 400
                val msg = "VOXPC_DISCOVER".toByteArray()
                socket.send(DatagramPacket(msg, msg.size, InetAddress.getByName("255.255.255.255"), PORT))
                val buf = ByteArray(2048)
                val end = System.currentTimeMillis() + timeoutMs
                while (System.currentTimeMillis() < end) {
                    try {
                        val p = DatagramPacket(buf, buf.size)
                        socket.receive(p)
                        val ip = p.address?.hostAddress ?: continue
                        val j = JSONObject(String(p.data, 0, p.length, Charsets.UTF_8))
                        if (found.none { it.ip == ip }) {
                            found += FoundPc(ip, j.optString("name", ip), j.optInt("port", 47800), j.optString("mac"))
                        }
                    } catch (e: SocketTimeoutException) {
                    } catch (e: Exception) {
                    }
                }
            }
        } catch (e: Exception) {
        }
        found
    }
}
