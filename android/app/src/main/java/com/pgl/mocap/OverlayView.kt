package com.pgl.mocap

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View

/** Показывает кадр камеры и скелеты поверх него. */
class OverlayView @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null) : View(context, attrs) {
    private var frame: Bitmap? = null
    private var poses: List<Pose?> = emptyList()
    private var mirror = false

    private val slotColors = intArrayOf(Color.rgb(163, 230, 53), Color.rgb(40, 170, 255), Color.rgb(255, 140, 60), Color.rgb(220, 80, 220))
    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeWidth = 6f; style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
    private val dotPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; style = Paint.Style.FILL }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 42f; isFakeBoldText = true }
    private val bmpPaint = Paint(Paint.FILTER_BITMAP_FLAG)
    private val dst = RectF()

    /** Вызывается из любого потока. */
    fun update(bitmap: Bitmap, poses: List<Pose?>, mirror: Boolean) {
        post {
            frame = bitmap
            this.poses = poses
            this.mirror = mirror
            invalidate()
        }
    }

    fun clear() {
        post {
            frame = null
            poses = emptyList()
            invalidate()
        }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawColor(Color.rgb(12, 13, 16))
        val bmp = frame ?: return
        val sc = minOf(width.toFloat() / bmp.width, height.toFloat() / bmp.height)
        val w = bmp.width * sc
        val h = bmp.height * sc
        val left = (width - w) / 2
        val top = (height - h) / 2
        dst.set(left, top, left + w, top + h)

        canvas.save()
        if (mirror) canvas.scale(-1f, 1f, width / 2f, height / 2f)   // как в селфи-камере
        canvas.drawBitmap(bmp, null, dst, bmpPaint)
        for ((si, p) in poses.withIndex()) {
            if (p == null) continue
            val col = slotColors[si % slotColors.size]
            linePaint.color = col
            fun px(i: Int) = left + p.norm[i][0].toFloat() * w
            fun py(i: Int) = top + p.norm[i][1].toFloat() * h
            for ((a, b) in SKELETON) {
                if (p.vis[a] > 0.3 && p.vis[b] > 0.3) canvas.drawLine(px(a), py(a), px(b), py(b), linePaint)
            }
            for (i in 0 until 33) {
                if (p.vis[i] > 0.3) canvas.drawCircle(px(i), py(i), 7f, dotPaint)
            }
        }
        canvas.restore()

        // подписи P1..P4 рисуем без зеркала, чтобы текст читался
        for ((si, p) in poses.withIndex()) {
            if (p == null) continue
            val c = p.hipCenterNorm()
            var x = left + c[0].toFloat() * w
            if (mirror) x = width - x
            textPaint.color = slotColors[si % slotColors.size]
            canvas.drawText("P${si + 1}", x + 14f, top + c[1].toFloat() * h, textPaint)
        }
    }
}
