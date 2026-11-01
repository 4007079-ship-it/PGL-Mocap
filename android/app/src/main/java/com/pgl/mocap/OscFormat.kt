package com.pgl.mocap

import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer

/** Сообщение OSC: адрес + float-аргументы (Aximmetry читает float32). */
class OscMessage(val address: String, val args: FloatArray) {
    fun encode(): ByteArray {
        val out = ByteArrayOutputStream()
        writePadded(out, address.toByteArray(Charsets.UTF_8))
        writePadded(out, ("," + "f".repeat(args.size)).toByteArray(Charsets.US_ASCII))
        val bb = ByteBuffer.allocate(4 * args.size)   // big-endian по умолчанию
        for (a in args) bb.putFloat(a)
        out.write(bb.array())
        return out.toByteArray()
    }

    private fun writePadded(out: ByteArrayOutputStream, b: ByteArray) {
        out.write(b)
        val pad = 4 - (b.size % 4)          // минимум один нулевой байт
        repeat(pad) { out.write(0) }
    }
}

/**
 * Формирует OSC-сообщения кадра — те же адреса и значения, что у компьютерной версии
 * (см. pglmocap/osc_output.py):
 *   /pglmocap/count, /pglmocap/pN/detected, /pglmocap/pN/<точка>, .../vis,
 *   /pglmocap/pN/hip_center, shoulder_center, screen_pos, all
 */
object OscFormat {
    fun screenCoords(norm: Array<DoubleArray>, aspect: Double) = Array(norm.size) { i ->
        doubleArrayOf((norm[i][0] - 0.5) * aspect, 0.5 - norm[i][1], -norm[i][2] * aspect)
    }

    fun worldCoords(world: Array<DoubleArray>) = Array(world.size) { i ->
        doubleArrayOf(world[i][0], -world[i][1], -world[i][2])
    }

    fun transform(pts: Array<DoubleArray>, s: Settings) = Array(pts.size) { i ->
        var x = pts[i][0] * s.scale
        var y = pts[i][1] * s.scale
        var z = pts[i][2] * s.scale
        if (s.flipX) x = -x
        if (s.upAxis == "z") {
            val ny = -z
            val nz = y
            y = ny
            z = nz
        }
        doubleArrayOf(x + s.offsetX, y + s.offsetY, z + s.offsetZ)
    }

    private fun f3(v: DoubleArray) = floatArrayOf(v[0].toFloat(), v[1].toFloat(), v[2].toFloat())

    fun buildFrame(poses: List<Pose?>, aspect: Double, s: Settings, maxSlots: Int): List<OscMessage> {
        val pre = s.oscPrefix.trimEnd('/')
        val names = if (s.jointSet == "all") LANDMARK_NAMES else CORE_JOINTS
        val msgs = ArrayList<OscMessage>()
        msgs.add(OscMessage("$pre/count", floatArrayOf(poses.count { it != null }.toFloat())))
        for (slot in 0 until maxSlots) {
            val base = "$pre/p${slot + 1}"
            val pose = poses.getOrNull(slot)
            if (pose == null) {
                msgs.add(OscMessage("$base/detected", floatArrayOf(0f)))
                continue
            }
            msgs.add(OscMessage("$base/detected", floatArrayOf(1f)))
            val screen = screenCoords(pose.norm, aspect)
            val raw = if (s.coordMode == "screen") screen else worldCoords(pose.world)
            val pts = transform(raw, s)
            for (name in names) {
                val i = IDX.getValue(name)
                msgs.add(OscMessage("$base/$name", f3(pts[i])))
                if (s.sendVisibility) msgs.add(OscMessage("$base/$name/vis", floatArrayOf(pose.vis[i].toFloat())))
            }
            val hip = V.mid(pts[IDX.getValue("left_hip")], pts[IDX.getValue("right_hip")])
            val sh = V.mid(pts[IDX.getValue("left_shoulder")], pts[IDX.getValue("right_shoulder")])
            msgs.add(OscMessage("$base/hip_center", f3(hip)))
            msgs.add(OscMessage("$base/shoulder_center", f3(sh)))
            val scr = transform(screen, s)
            msgs.add(OscMessage("$base/screen_pos", f3(V.mid(scr[IDX.getValue("left_hip")], scr[IDX.getValue("right_hip")]))))
            if (s.sendAllVector) {
                val all = FloatArray(names.size * 3)
                names.forEachIndexed { k, n -> val p = pts[IDX.getValue(n)]; for (j in 0..2) all[k * 3 + j] = p[j].toFloat() }
                msgs.add(OscMessage("$base/all", all))
            }
        }
        return msgs
    }
}
