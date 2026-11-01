package com.pgl.mocap

import android.content.Context
import android.graphics.Bitmap
import android.os.SystemClock
import android.util.Log
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarker

/** Обёртка над MediaPipe Pose Landmarker (режим VIDEO, вызывается из потока анализа). */
class PoseDetector(context: Context, model: String, numPoses: Int, minConfidence: Double, useGpu: Boolean) {
    private val landmarker: PoseLandmarker
    private var lastTs = -1L
    val usingGpu: Boolean

    init {
        val asset = "pose_landmarker_$model.task"
        fun build(delegate: Delegate): PoseLandmarker {
            val base = BaseOptions.builder().setModelAssetPath(asset).setDelegate(delegate).build()
            val c = minConfidence.toFloat()
            val options = PoseLandmarker.PoseLandmarkerOptions.builder()
                .setBaseOptions(base)
                .setRunningMode(RunningMode.VIDEO)
                .setNumPoses(numPoses)
                .setMinPoseDetectionConfidence(c)
                .setMinPosePresenceConfidence(c)
                .setMinTrackingConfidence(c)
                .build()
            return PoseLandmarker.createFromOptions(context, options)
        }
        var gpu = false
        landmarker = if (useGpu) {
            try {
                build(Delegate.GPU).also { gpu = true }
            } catch (e: Exception) {
                Log.w("PGLMocap", "GPU недоступен, используется CPU: ${e.message}")
                build(Delegate.CPU)
            }
        } else {
            build(Delegate.CPU)
        }
        usingGpu = gpu
    }

    fun detect(bitmap: Bitmap): List<Pose> {
        var ts = SystemClock.uptimeMillis()
        if (ts <= lastTs) ts = lastTs + 1
        lastTs = ts
        val result = landmarker.detectForVideo(BitmapImageBuilder(bitmap).build(), ts)
        val out = ArrayList<Pose>()
        val lmsAll = result.landmarks()
        val worldAll = result.worldLandmarks()
        for ((i, lms) in lmsAll.withIndex()) {
            if (lms.size < 33) continue
            val norm = Array(33) { k -> doubleArrayOf(lms[k].x().toDouble(), lms[k].y().toDouble(), lms[k].z().toDouble()) }
            val vis = DoubleArray(33) { k -> lms[k].visibility().orElse(1f).toDouble() }
            val world = if (i < worldAll.size && worldAll[i].size >= 33) {
                val w = worldAll[i]
                Array(33) { k -> doubleArrayOf(w[k].x().toDouble(), w[k].y().toDouble(), w[k].z().toDouble()) }
            } else {
                Array(33) { DoubleArray(3) }
            }
            out.add(Pose(norm, world, vis))
        }
        return out
    }

    fun close() = landmarker.close()
}
