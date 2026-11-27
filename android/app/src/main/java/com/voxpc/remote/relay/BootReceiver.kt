package com.voxpc.remote.relay

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.voxpc.remote.data.Prefs

/** После перезагрузки телефона снова запускает ретранслятор, если он был включён. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED && Prefs(context).relayMode) {
            runCatching { RelayService.start(context) }
        }
    }
}
