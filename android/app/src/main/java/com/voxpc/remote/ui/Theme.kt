package com.voxpc.remote.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Bg = Color(0xFF0B0D12)
val Panel = Color(0xFF12151E)
val CardC = Color(0xFF181D2A)
val CardHi = Color(0xFF222939)
val Accent = Color(0xFF7C5CFF)
val AccentHi = Color(0xFF9B82FF)
val Cyan = Color(0xFF22D3EE)
val TextC = Color(0xFFE6E8EF)
val Muted = Color(0xFF8A93A6)
val Ok = Color(0xFF2EE59D)
val Danger = Color(0xFFFF5C7A)
val Warn = Color(0xFFFFC857)

private val scheme = darkColorScheme(
    primary = Accent,
    onPrimary = Color.White,
    secondary = Cyan,
    background = Bg,
    onBackground = TextC,
    surface = CardC,
    onSurface = TextC,
    surfaceVariant = CardHi,
    onSurfaceVariant = Muted,
    error = Danger,
    outline = CardHi,
)

@Composable
fun VoxTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = scheme, content = content)
}
