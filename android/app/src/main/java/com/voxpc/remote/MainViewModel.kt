package com.voxpc.remote

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.voxpc.remote.data.Prefs
import com.voxpc.remote.net.Discovery
import com.voxpc.remote.net.FoundPc
import com.voxpc.remote.net.Keenetic
import com.voxpc.remote.net.WakeRelay
import com.voxpc.remote.relay.RelayService
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
    val remote: Boolean = false,
    val pcName: String = "",
    val apps: List<PcApp> = emptyList(),
    val log: List<LogEntry> = emptyList(),
    val busy: Boolean = false,
    val waking: Boolean = false,
    val searching: Boolean = false,
    val searched: Boolean = false,
    val relayMode: Boolean = false,
    val found: List<FoundPc> = emptyList(),
)

private val WAKE_PHRASES = listOf(
    "включи компьютер", "включи комп", "включи пк", "запусти компьютер", "запусти пк",
    "разбуди компьютер", "разбуди пк", "включить компьютер", "включи ноутбук",
)

class MainViewModel(app: Application) : AndroidViewModel(app) {
    val prefs = Prefs(app)
    val client = PcClient(prefs)
    private val _state = MutableStateFlow(
        UiState(configured = prefs.host.isNotBlank(), pcName = prefs.pcName, relayMode = prefs.relayMode)
    )
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
                online = p.online, checked = true, authorized = !p.online || p.authorized, remote = p.remote,
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
            // 1) в домашней сети — обычный «магический пакет»
            val local = WakeOnLan.send(prefs.mac, prefs.broadcast, prefs.wolPort, prefs.host)
            // 2) вне дома — через роутер
            when (prefs.routerType) {
                "keenetic" -> {
                    val r = Keenetic.wake(prefs.routerUrl, prefs.routerLogin, prefs.routerPassword, prefs.mac)
                    if (r.isSuccess) addLog("Роутер Keenetic разбудил ПК. Он загрузится через 15–60 секунд", true, false)
                    else addLog("Keenetic: ${r.exceptionOrNull()?.message}", false, false)
                }
                "relay" -> {
                    addLog("Отправляю команду домашнему телефону-ретранслятору…", true, false)
                    val r = WakeRelay.wake(prefs.remoteId, prefs.token) { status ->
                        when (status) {
                            "sent" -> addLog("Ретранслятор отправил сигнал. ПК загружается…", true, false)
                            "online" -> addLog("ПК включился!", true, false)
                            "denied" -> addLog("Ретранслятор отклонил команду: разные коды доступа", false, false)
                            "error" -> addLog("Ретранслятор не смог отправить сигнал", false, false)
                        }
                    }
                    if (r.isFailure) addLog("Ретранслятор: ${r.exceptionOrNull()?.message}", false, false)
                    else if (r.getOrNull() == false)
                        addLog("Домашний телефон не ответил. Он включён, в Wi-Fi и режим ретранслятора включён?", false, false)
                }
                "forward" -> if (prefs.wanHost.isNotBlank()) {
                    val r = WakeOnLan.send(prefs.mac, prefs.wanHost, prefs.wanPort, prefs.wanHost)
                    if (r.isSuccess) addLog("Сигнал включения отправлен на роутер (${prefs.wanHost})", true, false)
                    else addLog("Не удалось отправить на роутер: ${r.exceptionOrNull()?.message}", false, false)
                }
            }
            if (prefs.routerType == "none" || local.isFailure) {
                if (local.isSuccess) {
                    addLog("Сигнал включения отправлен. ПК загрузится через 15–60 секунд", true, false)
                } else {
                    addLog("Не удалось отправить сигнал: ${local.exceptionOrNull()?.message}", false, false)
                }
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
        if (pc.remoteId.isNotBlank()) prefs.remoteId = pc.remoteId
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

    fun saveRemote(type: String, url: String, login: String, password: String, wanHost: String, wanPort: String) {
        prefs.routerType = type
        prefs.routerUrl = url
        prefs.routerLogin = login
        prefs.routerPassword = password
        prefs.wanHost = wanHost
        prefs.wanPort = wanPort.toIntOrNull() ?: 9
    }

    fun setRelayMode(on: Boolean) {
        prefs.relayMode = on
        val ctx = getApplication<Application>()
        if (on) RelayService.start(ctx) else RelayService.stop(ctx)
        _state.update { it.copy(relayMode = on) }
    }

    fun clearLog() = _state.update { it.copy(log = emptyList()) }

    private fun addLog(text: String, ok: Boolean, fromUser: Boolean) {
        val time = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
        val entry = LogEntry(logId++, time, text, ok, fromUser)
        _state.update { it.copy(log = (listOf(entry) + it.log).take(60)) }
    }
}
