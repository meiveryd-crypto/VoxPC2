package com.voxpc.remote

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import android.content.ActivityNotFoundException
import android.content.Intent
import android.os.Bundle
import android.speech.RecognizerIntent
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import com.voxpc.remote.ui.HomeScreen
import com.voxpc.remote.ui.ScreenView
import com.voxpc.remote.ui.SettingsScreen
import com.voxpc.remote.ui.VoxTheme

const val ACTION_WAKE = "com.voxpc.remote.WAKE"
const val ACTION_VOICE = "com.voxpc.remote.VOICE"

class MainActivity : ComponentActivity() {
    private val vm: MainViewModel by viewModels()
    private val pendingAction = mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (savedInstanceState == null) pendingAction.value = intent?.action
        setContent {
            VoxTheme {
                AppRoot(vm, pendingAction.value) { pendingAction.value = null }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        pendingAction.value = intent.action
    }

    override fun onStart() {
        super.onStart()
        vm.startPolling()
        if (vm.prefs.relayMode) runCatching { com.voxpc.remote.relay.RelayService.start(this) }
    }

    override fun onStop() {
        super.onStop()
        vm.stopPolling()
    }
}

/** Просит Android не усыплять приложение, чтобы ретранслятор всегда был на связи. */
@SuppressLint("BatteryLife")
private fun requestNoBatteryLimits(context: android.content.Context) {
    val pm = context.getSystemService(android.content.Context.POWER_SERVICE) as PowerManager
    if (!pm.isIgnoringBatteryOptimizations(context.packageName)) {
        runCatching {
            context.startActivity(
                Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${context.packageName}"))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        }
    }
}

@Composable
private fun AppRoot(vm: MainViewModel, shortcut: String?, onShortcutHandled: () -> Unit) {
    val state by vm.state.collectAsState()
    var screen by rememberSaveable { mutableStateOf("home") }
    val context = LocalContext.current

    val notifPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    val onRelayToggle: (Boolean) -> Unit = { on ->
        vm.setRelayMode(on)
        if (on) {
            if (Build.VERSION.SDK_INT >= 33) notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            requestNoBatteryLimits(context)
        }
    }
    val speech = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { res ->
        val text = res.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
        if (res.resultCode == Activity.RESULT_OK && !text.isNullOrBlank()) vm.onVoice(text)
    }
    val startVoice: () -> Unit = {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ru-RU")
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Скажите команду для компьютера")
        }
        try {
            speech.launch(intent)
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(context, "Распознавание речи недоступно: установите приложение Google", Toast.LENGTH_LONG).show()
        }
    }

    LaunchedEffect(shortcut) {
        when (shortcut) {
            ACTION_WAKE -> vm.wake()
            ACTION_VOICE -> startVoice()
        }
        if (shortcut != null) onShortcutHandled()
    }

    BackHandler(enabled = screen != "home") { screen = "home" }

    when (screen) {
        "screen" -> ScreenView(vm.client, state.remote, onBack = { screen = "home" })
        "settings" -> SettingsScreen(
            state = state,
            prefs = vm.prefs,
            onBack = { screen = "home" },
            onDiscover = vm::discover,
            onPick = vm::applyFound,
            onSave = vm::save,
            onSaveRemote = vm::saveRemote,
            onRelayToggle = onRelayToggle,
        )
        else -> HomeScreen(
            state = state,
            onMic = startVoice,
            onSend = vm::send,
            onWake = vm::wake,
            onAction = { action, label, app -> vm.action(action, label, app) },
            onSettings = { screen = "settings" },
            onClearLog = vm::clearLog,
            onScreen = { screen = "screen" },
        )
    }
}
