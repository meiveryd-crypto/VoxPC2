package com.voxpc.remote.ui

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Send
import androidx.compose.material.icons.automirrored.rounded.VolumeDown
import androidx.compose.material.icons.automirrored.rounded.VolumeOff
import androidx.compose.material.icons.automirrored.rounded.VolumeUp
import androidx.compose.material.icons.rounded.Bedtime
import androidx.compose.material.icons.rounded.DesktopWindows
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.PowerSettingsNew
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material.icons.rounded.SkipPrevious
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.voxpc.remote.LogEntry
import com.voxpc.remote.UiState
import com.voxpc.remote.net.PcApp

@Composable
fun HomeScreen(
    state: UiState,
    onMic: () -> Unit,
    onSend: (String) -> Unit,
    onWake: () -> Unit,
    onAction: (action: String, label: String, app: String?) -> Unit,
    onSettings: () -> Unit,
    onClearLog: () -> Unit,
    onScreen: () -> Unit = {},
) {
    var input by rememberSaveable { mutableStateOf("") }
    var confirm by remember { mutableStateOf<Pair<String, String>?>(null) }

    Box(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(Color(0xFF1A1440), Bg, Bg)))
    ) {
        LazyColumn(
            modifier = Modifier.fillMaxSize().systemBarsPadding().imePadding(),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item { Header(state, onSettings) }
            if (state.busy) item { LinearProgressIndicator(Modifier.fillMaxWidth().clip(CircleShape), color = Accent) }

            if (!state.configured) {
                item {
                    InfoCard(
                        "Подключите компьютер",
                        "Запустите VoxPC на ПК, затем нажмите «Найти ПК» в настройках.",
                        Accent, "Открыть настройки", onSettings,
                    )
                }
            } else if (state.online && !state.authorized) {
                item {
                    InfoCard(
                        "Неверный код доступа",
                        "Введите код из окна VoxPC на компьютере (Настройки → Код доступа).",
                        Warn, "Ввести код", onSettings,
                    )
                }
            }

            item { PowerCard(state, onWake) { action, label -> confirm = action to label } }
            if (state.online && state.authorized) {
                item {
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(CardC)
                            .clickable(onClick = onScreen).padding(18.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Rounded.DesktopWindows, null, tint = Cyan)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text("Экран ПК", color = TextC, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                            Text(if (state.remote) "Смотреть через интернет" else "Смотреть, что происходит на компьютере",
                                color = Muted, fontSize = 13.sp)
                        }
                        Text("Открыть", color = Accent, fontWeight = FontWeight.Bold)
                    }
                }
            }
            item { MicCard(state, onMic) }

            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = input,
                        onValueChange = { input = it },
                        modifier = Modifier.weight(1f),
                        placeholder = { Text("Команда текстом: открой дискорд") },
                        singleLine = true,
                        shape = RoundedCornerShape(16.dp),
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = { onSend(input); input = "" }),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedContainerColor = CardC, unfocusedContainerColor = CardC,
                            focusedBorderColor = Accent, unfocusedBorderColor = Color.Transparent,
                        ),
                    )
                    Spacer(Modifier.width(10.dp))
                    Box(
                        Modifier.size(56.dp).clip(RoundedCornerShape(16.dp)).background(Accent)
                            .clickable { onSend(input); input = "" },
                        contentAlignment = Alignment.Center,
                    ) { Icon(Icons.AutoMirrored.Rounded.Send, "Отправить", tint = Color.White) }
                }
            }

            item { MediaCard { action, label -> onAction(action, label, null) } }

            if (state.apps.isNotEmpty()) {
                item {
                    SectionTitle("Приложения", "Нажмите — открыть, удерживайте — закрыть")
                }
                items(state.apps.chunked(3)) { row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        row.forEach { app ->
                            AppTile(
                                app, Modifier.weight(1f),
                                onOpen = { onAction("open_app", "Открыть ${app.name}", app.name) },
                                onClose = { onAction("close_app", "Закрыть ${app.name}", app.name) },
                            )
                        }
                        repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                    }
                }
            }

            if (state.log.isNotEmpty()) {
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        SectionTitle("История", null, Modifier.weight(1f))
                        TextButton(onClick = onClearLog) { Text("Очистить", color = Muted) }
                    }
                }
                items(state.log, key = { it.id }) { LogRow(it) }
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }

    confirm?.let { (action, label) ->
        AlertDialog(
            onDismissRequest = { confirm = null },
            containerColor = CardC,
            title = { Text(label) },
            text = { Text("Выполнить на компьютере «${state.pcName.ifBlank { "ПК" }}»?") },
            confirmButton = {
                TextButton(onClick = { onAction(action, label, null); confirm = null }) {
                    Text("Да", color = if (action == "shutdown") Danger else Accent)
                }
            },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("Отмена", color = Muted) } },
        )
    }
}

@Composable
private fun Header(state: UiState, onSettings: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 8.dp)) {
        Column(Modifier.weight(1f)) {
            Text("VoxPC", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = TextC)
            Text(
                state.pcName.ifBlank { if (state.configured) "Компьютер" else "ПК не подключён" },
                color = Muted, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
        }
        StatusChip(state)
        Spacer(Modifier.width(8.dp))
        IconButton(onClick = onSettings, modifier = Modifier.clip(CircleShape).background(CardC)) {
            Icon(Icons.Rounded.Settings, "Настройки", tint = TextC)
        }
    }
}

@Composable
private fun StatusChip(state: UiState) {
    val (text, color) = when {
        !state.configured -> "Нет ПК" to Muted
        !state.checked -> "Проверка…" to Muted
        state.online && state.remote -> "В сети · интернет" to Ok
        state.online -> "В сети" to Ok
        state.waking -> "Включается…" to Warn
        else -> "Выключен" to Danger
    }
    Row(
        Modifier.clip(CircleShape).background(color.copy(alpha = 0.15f)).padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(color))
        Spacer(Modifier.width(6.dp))
        Text(text, color = color, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun InfoCard(title: String, text: String, color: Color, button: String, onClick: () -> Unit) {
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(color.copy(alpha = 0.12f)).padding(18.dp)
    ) {
        Text(title, color = color, fontWeight = FontWeight.Bold, fontSize = 17.sp)
        Text(text, color = TextC, fontSize = 14.sp, modifier = Modifier.padding(top = 4.dp, bottom = 10.dp))
        Box(
            Modifier.clip(RoundedCornerShape(12.dp)).background(color).clickable(onClick = onClick)
                .padding(horizontal = 16.dp, vertical = 10.dp)
        ) { Text(button, color = Bg, fontWeight = FontWeight.Bold) }
    }
}

@Composable
private fun PowerCard(state: UiState, onWake: () -> Unit, onConfirm: (String, String) -> Unit) {
    val online = state.online
    val ring = if (online) Ok else if (state.waking) Warn else Accent
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(CardC).padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier.size(112.dp).clip(CircleShape)
                .background(Brush.radialGradient(listOf(ring.copy(alpha = 0.45f), ring.copy(alpha = 0.08f))))
                .clickable(enabled = !online && !state.waking) { onWake() },
            contentAlignment = Alignment.Center,
        ) {
            Box(
                Modifier.size(80.dp).clip(CircleShape).background(ring),
                contentAlignment = Alignment.Center,
            ) { Icon(Icons.Rounded.PowerSettingsNew, null, tint = Color.White, modifier = Modifier.size(40.dp)) }
        }
        Spacer(Modifier.height(12.dp))
        Text(
            when {
                online -> "Компьютер включён"
                state.waking -> "Отправлен сигнал включения…"
                else -> "Нажмите, чтобы включить ПК"
            },
            color = TextC, fontWeight = FontWeight.SemiBold, fontSize = 16.sp,
        )
        if (online) {
            Spacer(Modifier.height(14.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                PowerBtn(Icons.Rounded.Lock, "Блок", Modifier.weight(1f)) { onConfirm("lock", "Заблокировать") }
                PowerBtn(Icons.Rounded.Bedtime, "Сон", Modifier.weight(1f)) { onConfirm("sleep", "Спящий режим") }
                PowerBtn(Icons.Rounded.RestartAlt, "Рестарт", Modifier.weight(1f)) { onConfirm("restart", "Перезагрузить") }
                PowerBtn(Icons.Rounded.PowerSettingsNew, "Выкл", Modifier.weight(1f), Danger) {
                    onConfirm("shutdown", "Выключить компьютер")
                }
            }
        }
    }
}

@Composable
private fun PowerBtn(icon: ImageVector, label: String, modifier: Modifier, tint: Color = TextC, onClick: () -> Unit) {
    Column(
        modifier.clip(RoundedCornerShape(16.dp)).background(CardHi).clickable(onClick = onClick).padding(vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(icon, label, tint = tint)
        Text(label, color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
    }
}

@Composable
private fun MicCard(state: UiState, onMic: () -> Unit) {
    val transition = rememberInfiniteTransition(label = "pulse")
    val pulse by transition.animateFloat(
        initialValue = 1f, targetValue = 1.12f,
        animationSpec = infiniteRepeatable(tween(1300, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "scale",
    )
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp))
            .background(Brush.linearGradient(listOf(Color(0xFF2A1F6B), Color(0xFF15233F))))
            .padding(vertical = 26.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(contentAlignment = Alignment.Center) {
            Box(Modifier.size(132.dp).scale(pulse).clip(CircleShape).background(Accent.copy(alpha = 0.18f)))
            Box(Modifier.size(112.dp).clip(CircleShape).background(Accent.copy(alpha = 0.28f)))
            Box(
                Modifier.size(92.dp).clip(CircleShape)
                    .background(Brush.linearGradient(listOf(AccentHi, Accent)))
                    .clickable(onClick = onMic),
                contentAlignment = Alignment.Center,
            ) { Icon(Icons.Rounded.Mic, "Голосовая команда", tint = Color.White, modifier = Modifier.size(44.dp)) }
        }
        Spacer(Modifier.height(14.dp))
        Text("Нажмите и скажите команду", color = TextC, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
        Text(
            "«открой стим» · «громкость 40» · «включи компьютер»",
            color = Muted, fontSize = 13.sp, textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 4.dp, start = 16.dp, end = 16.dp),
        )
    }
}

@Composable
private fun MediaCard(onAction: (String, String) -> Unit) {
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(CardC).padding(14.dp)) {
        Text("Медиа и звук", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(start = 6.dp, bottom = 8.dp))
        Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            MediaBtn(Icons.Rounded.SkipPrevious, "Назад") { onAction("prev", "Предыдущий трек") }
            MediaBtn(Icons.Rounded.PlayArrow, "Пауза", big = true) { onAction("play_pause", "Пауза / воспроизведение") }
            MediaBtn(Icons.Rounded.SkipNext, "Вперёд") { onAction("next", "Следующий трек") }
            MediaBtn(Icons.AutoMirrored.Rounded.VolumeDown, "Тише") { onAction("vol_down", "Тише") }
            MediaBtn(Icons.AutoMirrored.Rounded.VolumeOff, "Звук") { onAction("mute", "Без звука") }
            MediaBtn(Icons.AutoMirrored.Rounded.VolumeUp, "Громче") { onAction("vol_up", "Громче") }
            MediaBtn(Icons.Rounded.DesktopWindows, "Свернуть") { onAction("desktop", "Свернуть окна") }
        }
    }
}

@Composable
private fun MediaBtn(icon: ImageVector, label: String, big: Boolean = false, onClick: () -> Unit) {
    Box(
        Modifier.size(if (big) 48.dp else 42.dp).clip(CircleShape).background(if (big) Accent else CardHi)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Icon(icon, label, tint = Color.White, modifier = Modifier.size(if (big) 28.dp else 22.dp)) }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun AppTile(app: PcApp, modifier: Modifier, onOpen: () -> Unit, onClose: () -> Unit) {
    Column(
        modifier.clip(RoundedCornerShape(20.dp)).background(CardC)
            .combinedClickable(onClick = onOpen, onLongClick = onClose)
            .padding(vertical = 16.dp, horizontal = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(app.icon.ifBlank { "🧩" }, fontSize = 30.sp)
        Text(
            app.name, color = TextC, fontSize = 13.sp, fontWeight = FontWeight.Medium, maxLines = 1,
            overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 6.dp),
        )
    }
}

@Composable
private fun SectionTitle(title: String, subtitle: String?, modifier: Modifier = Modifier) {
    Column(modifier.padding(top = 4.dp)) {
        Text(title, color = TextC, fontWeight = FontWeight.Bold, fontSize = 19.sp)
        if (subtitle != null) Text(subtitle, color = Muted, fontSize = 13.sp)
    }
}

@Composable
private fun LogRow(e: LogEntry) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = if (e.fromUser) Arrangement.End else Arrangement.Start,
    ) {
        Column(
            Modifier.clip(RoundedCornerShape(16.dp))
                .background(if (e.fromUser) Accent.copy(alpha = 0.22f) else CardC)
                .padding(horizontal = 14.dp, vertical = 10.dp)
        ) {
            Text(
                e.text, fontSize = 14.sp,
                color = when {
                    e.fromUser -> TextC
                    e.ok -> Ok
                    else -> Danger
                },
            )
            Text(e.time, color = Muted, fontSize = 11.sp, modifier = Modifier.align(Alignment.End))
        }
    }
}
