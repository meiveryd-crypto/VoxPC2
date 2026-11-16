package com.voxpc.remote

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.voxpc.remote.data.Prefs
import com.voxpc.remote.net.Discovery
import com.voxpc.remote.net.FoundPc
import com.voxpc.remote.net.PcApp
import com.voxpc.remote.net.PcClient
import com.voxpc.remote.net.WakeOnLan
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

data class LogEntry(val id: Long, val time: String, val text: String, val ok: Boolean, val fromUser: Boolean)

data class UiState(
    val configured: Boolean = false,
    val online: Boolean = false,
    val checked: Boolean = false,
    val authorized: Boolean = true,
    val pcName: String = "",
    val apps: List<PcApp> = emptyList(),
    val log: List<LogEntry> = emptyList(),
    val busy: Boolean = false,
    val waking: Boolean = false,
    val searching: Boolean = false,
    val searched: Boolean = false,
    val found: List<FoundPc> = emptyList(),
)

private val WAKE_PHRASES = listOf(
    "включи компьютер", "включи комп", "включи пк", "запусти компьютер", "запусти пк",
    "разбуди компьютер", "разбуди пк", "включить компьютер", "включи ноутбук",
)

class MainViewModel(app: Application) : AndroidViewModel(app) {
    val prefs = Prefs(app)
    private val client = PcClient(prefs)
    private val _state = MutableStateFlow(UiState(configured = prefs.host.isNotBlank(), pcName = prefs.pcName))
    val state = _state.asStateFlow()
    private var pollJob: Job? = null
    private var logId = 0L

    fun startPolling() {
        if (pollJob?.isActive == true) return
        pollJob = viewModelScope.launch {
            while (isActive) {
                refresh()
                delay(3000)
            }
        }
    }

    fun stopPolling() {
        pollJob?.cancel()
    }

    private suspend fun refresh() {
        val p = client.ping()
        val wasOnline = _state.value.online
        if (p.online && p.name.isNotBlank()) prefs.pcName = p.name
        _state.update {
            it.copy(
                online = p.online, checked = true, authorized = !p.online || p.authorized,
                pcName = p.name.ifBlank { it.pcName }, configured = prefs.host.isNotBlank(),
            )
        }
        if (p.online && p.authorized && (!wasOnline || _state.value.apps.isEmpty())) {
            val apps = client.apps()
            _state.update { it.copy(apps = apps) }
        }
    }

    /** Текст из распознавания речи. «Включи компьютер» обрабатывается на телефоне (Wake-on-LAN). */
    fun onVoice(text: String) {
        val t = text.lowercase(Locale.getDefault()).replace('ё', 'е')
        if (WAKE_PHRASES.any { it in t } || (!_state.value.online && t.startsWith("включи") && "компьютер" in t)) {
            addLog(text, ok = true, fromUser = true)
            wake()
        } else {
            send(text)
        }
    }

    fun send(text: String) {
        if (text.isBlank()) return
        addLog(text, ok = true, fromUser = true)
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            val r = client.command(text)
            addLog(r.message, r.ok, fromUser = false)
            _state.update { it.copy(busy = false) }
        }
    }

    fun action(action: String, label: String, app: String? = null) {
        addLog(label, ok = true, fromUser = true)
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            val r = client.action(action, app)
            addLog(r.message, r.ok, fromUser = false)
            _state.update { it.copy(busy = false) }
        }
    }

    fun wake() {
        viewModelScope.launch {
            _state.update { it.copy(waking = true) }
            val r = WakeOnLan.send(prefs.mac, prefs.broadcast, prefs.wolPort, prefs.host)
            if (r.isSuccess) {
                addLog("Сигнал включения отправлен. ПК загрузится через 15–60 секунд", true, false)
            } else {
                addLog("Не удалось отправить сигнал: ${r.exceptionOrNull()?.message}", false, false)
            }
            delay(4000)
            _state.update { it.copy(waking = false) }
        }
    }

    fun discover() {
        viewModelScope.launch {
            _state.update { it.copy(searching = true, found = emptyList()) }
            val list = Discovery.find()
            _state.update { it.copy(searching = false, searched = true, found = list) }
        }
    }

    fun applyFound(pc: FoundPc) {
        prefs.host = pc.ip
        prefs.port = pc.port
        if (pc.mac.isNotBlank()) prefs.mac = pc.mac
        prefs.pcName = pc.name
        _state.update { it.copy(configured = true, pcName = pc.name, found = emptyList(), apps = emptyList()) }
        viewModelScope.launch { refresh() }
    }

    fun save(host: String, port: String, token: String, mac: String, broadcast: String, wolPort: String) {
        prefs.host = host
        prefs.port = port.toIntOrNull() ?: 47800
        prefs.token = token
        prefs.mac = mac
        prefs.broadcast = broadcast
        prefs.wolPort = wolPort.toIntOrNull() ?: 9
        _state.update { it.copy(configured = host.isNotBlank(), apps = emptyList()) }
        viewModelScope.launch { refresh() }
    }

    fun clearLog() = _state.update { it.copy(log = emptyList()) }

    private fun addLog(text: String, ok: Boolean, fromUser: Boolean) {
        val time = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
        val entry = LogEntry(logId++, time, text, ok, fromUser)
        _state.update { it.copy(log = (listOf(entry) + it.log).take(60)) }
    }
}
