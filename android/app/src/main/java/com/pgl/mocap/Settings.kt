package com.pgl.mocap

import android.content.SharedPreferences

/** Настройки. Значения по умолчанию совпадают с компьютерной версией PGL Mocap. */
data class Settings(
    // Камера и трекинг
    var frontCamera: Boolean = false,
    var model: String = "full",          // lite | full
    var numPoses: Int = 1,
    var minConfidence: Double = 0.5,
    var smoothing: Double = 0.5,
    var holdSeconds: Double = 0.3,
    var useGpu: Boolean = true,
    // Куда отправлять
    var targetIp: String = "192.168.1.100",
    // OSC / Aximmetry
    var oscEnabled: Boolean = true,
    var oscPort: Int = 7000,
    var oscPrefix: String = "/pglmocap",
    var coordMode: String = "screen",    // screen | world
    var upAxis: String = "y",            // y | z
    var scale: Double = 1.0,
    var flipX: Boolean = false,
    var offsetX: Double = 0.0,
    var offsetY: Double = 0.0,
    var offsetZ: Double = 0.0,
    var jointSet: String = "all",        // all | core
    var sendVisibility: Boolean = false,
    var sendAllVector: Boolean = false,
    // Unreal Live Link
    var llEnabled: Boolean = false,
    var llPort: Int = 54321,
    var llPrefix: String = "PGL",
    var llPoints: String = "all",        // all | core
    var llRootMotion: Double = 200.0,
) {
    fun save(p: SharedPreferences) {
        p.edit()
            .putBoolean("frontCamera", frontCamera).putString("model", model).putInt("numPoses", numPoses)
            .putFloat("minConfidence", minConfidence.toFloat()).putFloat("smoothing", smoothing.toFloat())
            .putFloat("holdSeconds", holdSeconds.toFloat()).putBoolean("useGpu", useGpu)
            .putString("targetIp", targetIp)
            .putBoolean("oscEnabled", oscEnabled).putInt("oscPort", oscPort).putString("oscPrefix", oscPrefix)
            .putString("coordMode", coordMode).putString("upAxis", upAxis).putFloat("scale", scale.toFloat())
            .putBoolean("flipX", flipX).putFloat("offsetX", offsetX.toFloat()).putFloat("offsetY", offsetY.toFloat())
            .putFloat("offsetZ", offsetZ.toFloat()).putString("jointSet", jointSet)
            .putBoolean("sendVisibility", sendVisibility).putBoolean("sendAllVector", sendAllVector)
            .putBoolean("llEnabled", llEnabled).putInt("llPort", llPort).putString("llPrefix", llPrefix)
            .putString("llPoints", llPoints).putFloat("llRootMotion", llRootMotion.toFloat())
            .apply()
    }

    companion object {
        fun load(p: SharedPreferences): Settings {
            val d = Settings()
            return Settings(
                frontCamera = p.getBoolean("frontCamera", d.frontCamera),
                model = p.getString("model", d.model) ?: d.model,
                numPoses = p.getInt("numPoses", d.numPoses),
                minConfidence = p.getFloat("minConfidence", d.minConfidence.toFloat()).toDouble(),
                smoothing = p.getFloat("smoothing", d.smoothing.toFloat()).toDouble(),
                holdSeconds = p.getFloat("holdSeconds", d.holdSeconds.toFloat()).toDouble(),
                useGpu = p.getBoolean("useGpu", d.useGpu),
                targetIp = p.getString("targetIp", d.targetIp) ?: d.targetIp,
                oscEnabled = p.getBoolean("oscEnabled", d.oscEnabled),
                oscPort = p.getInt("oscPort", d.oscPort),
                oscPrefix = p.getString("oscPrefix", d.oscPrefix) ?: d.oscPrefix,
                coordMode = p.getString("coordMode", d.coordMode) ?: d.coordMode,
                upAxis = p.getString("upAxis", d.upAxis) ?: d.upAxis,
                scale = p.getFloat("scale", d.scale.toFloat()).toDouble(),
                flipX = p.getBoolean("flipX", d.flipX),
                offsetX = p.getFloat("offsetX", 0f).toDouble(),
                offsetY = p.getFloat("offsetY", 0f).toDouble(),
                offsetZ = p.getFloat("offsetZ", 0f).toDouble(),
                jointSet = p.getString("jointSet", d.jointSet) ?: d.jointSet,
                sendVisibility = p.getBoolean("sendVisibility", d.sendVisibility),
                sendAllVector = p.getBoolean("sendAllVector", d.sendAllVector),
                llEnabled = p.getBoolean("llEnabled", d.llEnabled),
                llPort = p.getInt("llPort", d.llPort),
                llPrefix = p.getString("llPrefix", d.llPrefix) ?: d.llPrefix,
                llPoints = p.getString("llPoints", d.llPoints) ?: d.llPoints,
                llRootMotion = p.getFloat("llRootMotion", d.llRootMotion.toFloat()).toDouble(),
            )
        }
    }
}
