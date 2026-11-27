package com.voxpc.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Computer
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.voxpc.remote.UiState
import com.voxpc.remote.data.Prefs
import com.voxpc.remote.net.FoundPc

@Composable
fun SettingsScreen(
    state: UiState,
    prefs: Prefs,
    onBack: () -> Unit,
    onDiscover: () -> Unit,
    onPick: (FoundPc) -> Unit,
    onSave: (host: String, port: String, token: String, mac: String, broadcast: String, wolPort: String) -> Unit,
    onSaveRemote: (type: String, url: String, login: String, password: String, wanHost: String, wanPort: String) -> Unit,
    onRelayToggle: (Boolean) -> Unit = {},
) {
    var routerType by remember { mutableStateOf(prefs.routerType) }
    var routerUrl by remember { mutableStateOf(prefs.routerUrl) }
    var routerLogin by remember { mutableStateOf(prefs.routerLogin) }
    var routerPassword by remember { mutableStateOf(prefs.routerPassword) }
    var wanHost by remember { mutableStateOf(prefs.wanHost) }
    var wanPort by remember { mutableStateOf(prefs.wanPort.toString()) }
    var host by remember { mutableStateOf(prefs.host) }
    var port by remember { mutableStateOf(prefs.port.toString()) }
    var token by remember { mutableStateOf(prefs.token) }
    var mac by remember { mutableStateOf(prefs.mac) }
    var broadcast by remember { mutableStateOf(prefs.broadcast) }
    var wolPort by remember { mutableStateOf(prefs.wolPort.toString()) }

    // После выбора найденного ПК подтягиваем значения в поля
    LaunchedEffect(state.configured, state.pcName) {
        host = prefs.host
        port = prefs.port.toString()
        mac = prefs.mac
    }

    Column(
        Modifier.fillMaxSize().background(Bg).systemBarsPadding().imePadding()
            .verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack, modifier = Modifier.clip(CircleShape).background(CardC)) {
                Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Назад", tint = TextC)
            }
            Spacer(Modifier.width(12.dp))
            Text("Настройки", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = TextC)
        }

        // --- поиск ---
        Card {
            Text("Поиск ПК в сети", color = TextC, fontWeight = FontWeight.Bold, fontSize = 17.sp)
            Text("Телефон и компьютер должны быть в одной Wi-Fi сети, VoxPC на ПК — запущен.",
                color = Muted, fontSize = 13.sp)
            Spacer(Modifier.height(12.dp))
            Row(
                Modifier.clip(RoundedCornerShape(14.dp)).background(Accent)
                    .clickable(enabled = !state.searching, onClick = onDiscover)
                    .padding(horizontal = 18.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (state.searching) {
                    CircularProgressIndicator(Modifier.size(18.dp), color = Color.White, strokeWidth = 2.dp)
                } else {
                    Icon(Icons.Rounded.Search, null, tint = Color.White)
                }
                Spacer(Modifier.width(8.dp))
                Text(if (state.searching) "Ищу…" else "Найти ПК", color = Color.White, fontWeight = FontWeight.Bold)
            }
            state.found.forEach { pc ->
                Spacer(Modifier.height(10.dp))
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(CardHi)
                        .clickable { onPick(pc) }.padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Rounded.Computer, null, tint = Cyan)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(pc.name, color = TextC, fontWeight = FontWeight.SemiBold)
                        Text("${pc.ip}:${pc.port}", color = Muted, fontSize = 12.sp)
                    }
                    Text("Выбрать", color = Accent, fontWeight = FontWeight.Bold)
                }
            }
            if (state.searched && !state.searching && state.found.isEmpty()) {
                Text("ПК не найден. Проверьте, что VoxPC запущен, и разрешите его в брандмауэре Windows.",
                    color = Warn, fontSize = 13.sp, modifier = Modifier.padding(top = 10.dp))
            }
        }

        // --- подключение ---
        Card {
            Text("Подключение", color = TextC, fontWeight = FontWeight.Bold, fontSize = 17.sp)
            Field("IP-адрес или домен ПК", host, { host = it }, KeyboardType.Uri)
            Field("Порт", port, { port = it.filter(Char::isDigit) }, KeyboardType.Number)
            Field("Код доступа (из VoxPC на ПК)", token, { token = it.uppercase() }, KeyboardType.Ascii, caps = true)
        }

        // --- WoL ---
        Card {
            Text("Удалённое включение", color = TextC, fontWeight = FontWeight.Bold, fontSize = 17.sp)
            Text("MAC-адрес показан в VoxPC на ПК (Настройки). При поиске он заполняется сам.",
                color = Muted, fontSize = 13.sp)
            Field("MAC-адрес ПК", mac, { mac = it.uppercase() }, KeyboardType.Ascii, caps = true)
            Field("Адрес для пакета (пусто — авто)", broadcast, { broadcast = it }, KeyboardType.Uri)
            Field("Порт Wake-on-LAN", wolPort, { wolPort = it.filter(Char::isDigit) }, KeyboardType.Number)
            Text(
                "Через интернет: на роутере пробросьте UDP 9 и TCP 47800 на ПК, а в полях выше укажите " +
                    "внешний IP или домен (DDNS) роутера.",
                color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp),
            )
        }

        // --- вне дома ---
        Card {
            Text("Вне дома", color = TextC, fontWeight = FontWeight.Bold, fontSize = 17.sp)
            Text(
                if (prefs.remoteId.isNotBlank())
                    "Управление и экран: работают через интернет, если на ПК в VoxPC включён «Доступ через интернет» " +
                        "(Настройки → Коннектор Claude). Адрес подхватывается сам."
                else "Нажмите «Найти ПК», находясь дома, — телефон получит секретный ключ для доступа вне дома.",
                color = if (prefs.remoteId.isNotBlank()) Muted else Warn, fontSize = 13.sp,
            )
            Text("Включение ПК вне дома — через роутер:", color = TextC, fontSize = 14.sp,
                modifier = Modifier.padding(top = 12.dp, bottom = 6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("none" to "Нет", "relay" to "Телефон дома", "keenetic" to "Keenetic", "forward" to "Порт").forEach { (k, label) ->
                    Text(
                        label, color = if (routerType == k) Color.White else Muted, fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.clip(RoundedCornerShape(12.dp))
                            .background(if (routerType == k) Accent else CardHi)
                            .clickable { routerType = k }.padding(horizontal = 14.dp, vertical = 9.dp),
                    )
                }
            }
            when (routerType) {
                "relay" -> {
                    Text("Второй телефон лежит дома в Wi-Fi с включённым режимом «Ретранслятор» (ниже). " +
                        "Вне дома нажмите кнопку питания — команда уйдёт ему, а он включит ПК в домашней сети.",
                        color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
                }
                "keenetic" -> {
                    Text("Адрес KeenDNS вашего роутера и учётная запись с доступом к веб-интерфейсу. " +
                        "MAC-адрес ПК берётся из блока выше.", color = Muted, fontSize = 12.sp,
                        modifier = Modifier.padding(top = 8.dp))
                    Field("Адрес роутера (например, myhome.keenetic.link)", routerUrl, { routerUrl = it }, KeyboardType.Uri)
                    Field("Логин роутера", routerLogin, { routerLogin = it }, KeyboardType.Ascii)
                    Field("Пароль роутера", routerPassword, { routerPassword = it }, KeyboardType.Password, secret = true)
                }
                "forward" -> {
                    Text("На роутере (ASUS, TP-Link и др.): закрепите за ПК IP-адрес, пробросьте UDP-порт с внешней " +
                        "стороны на этот IP и привяжите IP к MAC (IP & MAC Binding / статический ARP). " +
                        "Ниже — внешний IP или DDNS-домен роутера.", color = Muted, fontSize = 12.sp,
                        modifier = Modifier.padding(top = 8.dp))
                    Field("Внешний адрес роутера (IP или домен)", wanHost, { wanHost = it }, KeyboardType.Uri)
                    Field("Внешний UDP-порт", wanPort, { wanPort = it.filter(Char::isDigit) }, KeyboardType.Number)
                }
            }
        }

        // --- режим ретранслятора ---
        Card {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Этот телефон — ретранслятор", color = TextC, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                    Text(
                        "Включите на старом телефоне, который всегда лежит дома на зарядке в Wi-Fi. " +
                            "Он будет ждать команду и включать ПК. Сначала нажмите «Найти ПК» и введите код доступа.",
                        color = Muted, fontSize = 12.sp,
                    )
                }
                Spacer(Modifier.width(10.dp))
                Switch(
                    checked = state.relayMode,
                    onCheckedChange = { on ->
                        onSave(host, port, token, mac, broadcast, wolPort)
                        onRelayToggle(on)
                    },
                    colors = SwitchDefaults.colors(checkedTrackColor = Accent),
                )
            }
            if (state.relayMode) {
                Text(prefs.relayLast.ifBlank { "Работает в фоне. В шторке уведомлений будет значок VoxPC." },
                    color = Ok, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
            }
        }

        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Accent)
                .clickable {
                    onSave(host, port, token, mac, broadcast, wolPort)
                    onSaveRemote(routerType, routerUrl, routerLogin, routerPassword, wanHost, wanPort)
                    onBack()
                }
                .padding(vertical = 16.dp),
            horizontalArrangement = Arrangement.Center,
        ) { Text("Сохранить", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 16.sp) }
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun Card(content: @Composable () -> Unit) {
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(CardC).padding(18.dp)) {
        content()
    }
}

@Composable
private fun Field(label: String, value: String, onChange: (String) -> Unit, type: KeyboardType, caps: Boolean = false,
                  secret: Boolean = false) {
    OutlinedTextField(
        visualTransformation = if (secret) PasswordVisualTransformation() else VisualTransformation.None,
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
        shape = RoundedCornerShape(14.dp),
        keyboardOptions = KeyboardOptions(
            keyboardType = type,
            capitalization = if (caps) KeyboardCapitalization.Characters else KeyboardCapitalization.None,
            autoCorrectEnabled = false,
        ),
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = CardHi, unfocusedContainerColor = CardHi,
            focusedBorderColor = Accent, unfocusedBorderColor = Color.Transparent,
            focusedLabelColor = Accent, unfocusedLabelColor = Muted,
        ),
    )
}
