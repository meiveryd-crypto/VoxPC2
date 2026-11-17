package com.voxpc.remote.data

import android.content.Context

/** Настройки подключения к ПК. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("voxpc", Context.MODE_PRIVATE)

    var host: String
        get() = sp.getString("host", "") ?: ""
        set(v) = sp.edit().putString("host", v.trim()).apply()

    var port: Int
        get() = sp.getInt("port", 47800)
        set(v) = sp.edit().putInt("port", v).apply()

    var token: String
        get() = sp.getString("token", "") ?: ""
        set(v) = sp.edit().putString("token", v.trim().uppercase()).apply()

    var mac: String
        get() = sp.getString("mac", "") ?: ""
        set(v) = sp.edit().putString("mac", v.trim().uppercase()).apply()

    /** Пусто = автоматически (255.255.255.255 и x.x.x.255 по IP ПК). */
    var broadcast: String
        get() = sp.getString("broadcast", "") ?: ""
        set(v) = sp.edit().putString("broadcast", v.trim()).apply()

    var wolPort: Int
        get() = sp.getInt("wol_port", 9)
        set(v) = sp.edit().putInt("wol_port", v).apply()

    /** Секретный канал, через который ПК сообщает адрес туннеля (приходит при «Найти ПК»). */
    var remoteId: String
        get() = sp.getString("remote_id", "") ?: ""
        set(v) = sp.edit().putString("remote_id", v.trim()).apply()

    var remoteUrl: String
        get() = sp.getString("remote_url", "") ?: ""
        set(v) = sp.edit().putString("remote_url", v.trim()).apply()

    /** none | keenetic | forward */
    var routerType: String
        get() = sp.getString("router_type", "none") ?: "none"
        set(v) = sp.edit().putString("router_type", v).apply()

    var routerUrl: String
        get() = sp.getString("router_url", "") ?: ""
        set(v) = sp.edit().putString("router_url", v.trim()).apply()

    var routerLogin: String
        get() = sp.getString("router_login", "") ?: ""
        set(v) = sp.edit().putString("router_login", v.trim()).apply()

    var routerPassword: String
        get() = sp.getString("router_password", "") ?: ""
        set(v) = sp.edit().putString("router_password", v).apply()

    var wanHost: String
        get() = sp.getString("wan_host", "") ?: ""
        set(v) = sp.edit().putString("wan_host", v.trim()).apply()

    var wanPort: Int
        get() = sp.getInt("wan_port", 9)
        set(v) = sp.edit().putInt("wan_port", v).apply()

    var pcName: String
        get() = sp.getString("pc_name", "") ?: ""
        set(v) = sp.edit().putString("pc_name", v).apply()
}
