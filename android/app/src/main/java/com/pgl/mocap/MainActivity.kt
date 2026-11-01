package com.pgl.mocap

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Matrix
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.os.Bundle
import android.os.SystemClock
import android.util.Size
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.RadioGroup
import android.widget.SeekBar
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import java.net.Inet4Address
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private lateinit var overlay: OverlayView
    private lateinit var status: TextView
    private lateinit var btnStart: Button
    private lateinit var panel: View

    @Volatile private var settings = Settings()
    private val prefs by lazy { getSharedPreferences("pgl_mocap", Context.MODE_PRIVATE) }

    private val analysisExecutor: ExecutorService = Executors.newSingleThreadExecutor()
    private var cameraProvider: ProcessCameraProvider? = null

    // Состояние конвейера (используется только в потоке анализа)
    private var detector: PoseDetector? = null
    private var slots: PoseSlots? = null
    private var sender: Sender? = null
    @Volatile private var running = false
    @Volatile private var rebuildDetector = true

    // Статистика для строки статуса
    @Volatile private var fps = 0.0
    @Volatile private var persons = 0
    @Volatile private var oscRate = 0.0
    @Volatile private var llRate = 0.0
    @Volatile private var gpuInUse = false
    @Volatile private var errorText: String? = null

    private val requestCamera = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) start() else status.text = "Нет доступа к камере — разрешите его в настройках телефона"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        overlay = findViewById(R.id.overlay)
        status = findViewById(R.id.status)
        btnStart = findViewById(R.id.btnStart)
        panel = findViewById(R.id.settingsPanel)

        settings = Settings.load(prefs)
        fillSettingsForm()

        findViewById<Button>(R.id.btnSettings).setOnClickListener {
            panel.visibility = if (panel.visibility == View.VISIBLE) View.GONE else View.VISIBLE
            if (panel.visibility == View.VISIBLE) fillSettingsForm()
        }
        findViewById<Button>(R.id.btnCamera).setOnClickListener {
            settings = settings.copy(frontCamera = !settings.frontCamera)
            settings.save(prefs)
            if (running) bindCamera()
        }
        findViewById<Button>(R.id.btnApply).setOnClickListener { applySettingsForm() }
        btnStart.setOnClickListener { if (running) stop() else ensurePermissionAndStart() }

        status.postDelayed(statusUpdater, 500)
        ensurePermissionAndStart()
    }

    // ------------------------------------------------------------------ запуск / остановка

    private fun ensurePermissionAndStart() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            start()
        } else {
            requestCamera.launch(Manifest.permission.CAMERA)
        }
    }

    private fun start() {
        running = true
        errorText = null
        btnStart.text = "Стоп"
        btnStart.setBackgroundResource(R.drawable.btn_danger)
        btnStart.setTextColor(0xFFFFFFFF.toInt())
        bindCamera()
    }

    private fun stop() {
        running = false
        cameraProvider?.unbindAll()
        btnStart.text = "Старт"
        btnStart.setBackgroundResource(R.drawable.btn_accent)
        btnStart.setTextColor(0xFF0D1411.toInt())
        overlay.clear()
        analysisExecutor.execute {
            detector?.close(); detector = null
            sender?.close(); sender = null
            slots = null
            rebuildDetector = true
        }
    }

    private fun bindCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            val provider = future.get()
            cameraProvider = provider
            val selector = if (settings.frontCamera) CameraSelector.DEFAULT_FRONT_CAMERA else CameraSelector.DEFAULT_BACK_CAMERA
            val resolution = ResolutionSelector.Builder()
                .setResolutionStrategy(ResolutionStrategy(Size(640, 480), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER))
                .build()
            val analysis = ImageAnalysis.Builder()
                .setResolutionSelector(resolution)
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                .build()
            analysis.setAnalyzer(analysisExecutor) { proxy -> analyze(proxy) }
            try {
                provider.unbindAll()
                provider.bindToLifecycle(this, selector, analysis)
            } catch (e: Exception) {
                errorText = "Камера: ${e.message}"
            }
        }, ContextCompat.getMainExecutor(this))
    }

    // ------------------------------------------------------------------ обработка кадра (поток анализа)

    private var frames = 0
    private var tStat = SystemClock.elapsedRealtime()
    private var oscBefore = 0L
    private var llBefore = 0L

    private fun analyze(proxy: ImageProxy) {
        try {
            if (!running) return
            val s = settings
            if (rebuildDetector || detector == null) {
                detector?.close()
                detector = PoseDetector(this, s.model, s.numPoses, s.minConfidence, s.useGpu)
                gpuInUse = detector!!.usingGpu
                slots = PoseSlots(s.numPoses)
                rebuildDetector = false
            }
            if (sender == null) sender = Sender()

            val bitmap = upright(proxy.toBitmap(), proxy.imageInfo.rotationDegrees)
            val aspect = bitmap.width.toDouble() / bitmap.height
            val poses = detector!!.detect(bitmap)
            val now = SystemClock.elapsedRealtime() / 1000.0
            val out = slots!!.assign(poses, now, s)
            sender!!.send(out, aspect, s)
            overlay.update(bitmap, out, mirror = s.frontCamera)

            frames++
            val t = SystemClock.elapsedRealtime()
            if (t - tStat >= 1000) {
                val dt = (t - tStat) / 1000.0
                fps = frames / dt
                persons = out.count { it != null }
                val snd = sender!!
                oscRate = (snd.oscMessages - oscBefore) / dt
                llRate = (snd.llPackets - llBefore) / dt
                oscBefore = snd.oscMessages
                llBefore = snd.llPackets
                errorText = snd.lastError?.let { "Сеть: $it" }
                frames = 0
                tStat = t
            }
        } catch (e: Exception) {
            errorText = "Ошибка: ${e.message ?: e.javaClass.simpleName}"
        } finally {
            proxy.close()
        }
    }

    /** Поворачивает кадр так, как его видит человек, держащий телефон. Кадр НЕ зеркалится. */
    private fun upright(src: Bitmap, rotation: Int): Bitmap {
        if (rotation == 0) return src
        val m = Matrix().apply { postRotate(rotation.toFloat()) }
        return Bitmap.createBitmap(src, 0, 0, src.width, src.height, m, true)
    }

    // ------------------------------------------------------------------ статус

    private val statusUpdater = object : Runnable {
        override fun run() {
            val s = settings
            status.text = when {
                !running -> "Остановлено"
                errorText != null -> errorText
                else -> buildString {
                    append(String.format("%.0f к/с · людей: %d", fps, persons))
                    if (s.oscEnabled) append(String.format(" · OSC: %.0f/с", oscRate))
                    if (s.llEnabled) append(String.format(" · Live Link: %.0f к/с", llRate))
                    append(if (gpuInUse) " · GPU" else " · CPU")
                    append(" → ${s.targetIp}")
                }
            }
            status.setTextColor(if (errorText != null && running) 0xFFE5534B.toInt() else 0xFF8B93A1.toInt())
            status.postDelayed(this, 500)
        }
    }

    // ------------------------------------------------------------------ форма настроек

    private fun fillSettingsForm() {
        val s = settings
        findViewById<EditText>(R.id.ip).setText(s.targetIp)
        findViewById<Switch>(R.id.oscEnabled).isChecked = s.oscEnabled
        findViewById<EditText>(R.id.oscPort).setText(s.oscPort.toString())
        findViewById<EditText>(R.id.oscPrefix).setText(s.oscPrefix)
        findViewById<RadioGroup>(R.id.coordMode).check(if (s.coordMode == "world") R.id.coordWorld else R.id.coordScreen)
        findViewById<RadioGroup>(R.id.upAxis).check(if (s.upAxis == "z") R.id.upZ else R.id.upY)
        findViewById<Switch>(R.id.llEnabled).isChecked = s.llEnabled
        findViewById<EditText>(R.id.llPort).setText(s.llPort.toString())
        findViewById<EditText>(R.id.llPrefix).setText(s.llPrefix)
        findViewById<RadioGroup>(R.id.model).check(if (s.model == "lite") R.id.modelLite else R.id.modelFull)
        findViewById<RadioGroup>(R.id.numPoses).check(
            when (s.numPoses) { 2 -> R.id.np2; 3 -> R.id.np3; 4 -> R.id.np4; else -> R.id.np1 })
        val sb = findViewById<SeekBar>(R.id.smoothing)
        val sl = findViewById<TextView>(R.id.smoothingLabel)
        sb.progress = (s.smoothing * 100).toInt()
        sl.text = "Сглаживание: ${sb.progress}%"
        sb.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                sl.text = "Сглаживание: $progress%"
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })
        findViewById<Switch>(R.id.useGpu).isChecked = s.useGpu
        findViewById<TextView>(R.id.phoneIp).text = phoneIp()?.let { "IP этого телефона: $it" } ?: "Телефон не подключён к сети"
        val ver = try { packageManager.getPackageInfo(packageName, 0).versionName } catch (e: Exception) { "" }
        findViewById<TextView>(R.id.version).text = "PGL Mocap для Android $ver"
    }

    private fun applySettingsForm() {
        val old = settings
        fun intOf(id: Int, def: Int) = findViewById<EditText>(id).text.toString().trim().toIntOrNull()?.takeIf { it in 1..65535 } ?: def
        val s = old.copy(
            targetIp = findViewById<EditText>(R.id.ip).text.toString().trim().ifEmpty { old.targetIp },
            oscEnabled = findViewById<Switch>(R.id.oscEnabled).isChecked,
            oscPort = intOf(R.id.oscPort, old.oscPort),
            oscPrefix = findViewById<EditText>(R.id.oscPrefix).text.toString().trim().ifEmpty { "/pglmocap" },
            coordMode = if (findViewById<RadioGroup>(R.id.coordMode).checkedRadioButtonId == R.id.coordWorld) "world" else "screen",
            upAxis = if (findViewById<RadioGroup>(R.id.upAxis).checkedRadioButtonId == R.id.upZ) "z" else "y",
            llEnabled = findViewById<Switch>(R.id.llEnabled).isChecked,
            llPort = intOf(R.id.llPort, old.llPort),
            llPrefix = findViewById<EditText>(R.id.llPrefix).text.toString().trim().ifEmpty { "PGL" },
            model = if (findViewById<RadioGroup>(R.id.model).checkedRadioButtonId == R.id.modelLite) "lite" else "full",
            numPoses = when (findViewById<RadioGroup>(R.id.numPoses).checkedRadioButtonId) {
                R.id.np2 -> 2; R.id.np3 -> 3; R.id.np4 -> 4; else -> 1 },
            smoothing = findViewById<SeekBar>(R.id.smoothing).progress / 100.0,
            useGpu = findViewById<Switch>(R.id.useGpu).isChecked,
        )
        settings = s
        s.save(prefs)
        if (s.model != old.model || s.numPoses != old.numPoses || s.useGpu != old.useGpu) rebuildDetector = true
        panel.visibility = View.GONE
        (getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager).hideSoftInputFromWindow(panel.windowToken, 0)
        Toast.makeText(this, "Настройки применены", Toast.LENGTH_SHORT).show()
    }

    private fun phoneIp(): String? {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val lp: LinkProperties = cm.getLinkProperties(cm.activeNetwork) ?: return null
        return lp.linkAddresses.map { it.address }.firstOrNull { it is Inet4Address && !it.isLoopbackAddress }?.hostAddress
    }

    override fun onDestroy() {
        super.onDestroy()
        status.removeCallbacks(statusUpdater)
        running = false
        analysisExecutor.execute {
            detector?.close()
            sender?.close()
        }
        analysisExecutor.shutdown()
    }
}
