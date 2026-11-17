package com.voxpc.remote.ui

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.voxpc.remote.net.PcClient
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

/** Просмотр экрана ПК: обновляемые снимки, масштаб двумя пальцами, двойной тап — сброс масштаба. */
@Composable
fun ScreenView(client: PcClient, remote: Boolean, onBack: () -> Unit) {
    var frame by remember { mutableStateOf<ImageBitmap?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var paused by remember { mutableStateOf(false) }
    var hq by remember { mutableStateOf(!remote) }
    var fps by remember { mutableStateOf(0f) }
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    val transform = rememberTransformableState { zoom, pan, _ ->
        scale = (scale * zoom).coerceIn(1f, 6f)
        offset = if (scale == 1f) Offset.Zero else offset + pan
    }

    LaunchedEffect(paused, hq) {
        var fails = 0
        while (isActive && !paused) {
            val t0 = System.currentTimeMillis()
            val bytes = client.screen(if (hq) 1920 else 1280, if (hq) 70 else 50)
            if (bytes != null) {
                val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                if (bmp != null) {
                    frame = bmp.asImageBitmap()
                    error = null
                    fails = 0
                }
            } else {
                fails++
                if (fails >= 3) error = "ПК не отвечает. Он включён и VoxPC запущен?"
            }
            val spent = System.currentTimeMillis() - t0
            fps = if (spent > 0) 1000f / maxOf(spent, 250) else 0f
            delay(maxOf(0L, 250L - spent))
        }
    }

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        val img = frame
        if (img != null) {
            Image(
                bitmap = img,
                contentDescription = "Экран ПК",
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .fillMaxSize()
                    .pointerInput(Unit) {
                        detectTapGestures(onDoubleTap = { scale = 1f; offset = Offset.Zero })
                    }
                    .transformable(transform)
                    .graphicsLayer(scaleX = scale, scaleY = scale, translationX = offset.x, translationY = offset.y),
            )
        } else if (error == null) {
            CircularProgressIndicator(Modifier.align(Alignment.Center), color = Accent)
        }
        error?.let {
            Text(it, color = Danger, modifier = Modifier.align(Alignment.Center).padding(24.dp))
        }

        Row(
            Modifier.fillMaxWidth().systemBarsPadding().padding(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack, modifier = Modifier.clip(CircleShape).background(Color(0xAA151926))) {
                Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Назад", tint = TextC)
            }
            Spacer(Modifier.weight(1f))
            Chip(if (remote) "через интернет" else "Wi-Fi", Muted) {}
            Spacer(Modifier.width(6.dp))
            Chip("%.1f к/с".format(fps), Muted) {}
            Spacer(Modifier.width(6.dp))
            Chip(if (hq) "Чётко" else "Быстро", Cyan) { hq = !hq }
            Spacer(Modifier.width(6.dp))
            Chip(if (paused) "▶ Пуск" else "❚❚ Пауза", Accent) { paused = !paused }
        }
    }
}

@Composable
private fun Chip(text: String, color: Color, onClick: () -> Unit) {
    Column(
        Modifier.clip(RoundedCornerShape(14.dp)).background(Color(0xCC151926)).clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.Center,
    ) { Text(text, color = color, fontSize = 13.sp, fontWeight = FontWeight.SemiBold) }
}
