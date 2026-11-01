package com.pgl.mocap

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import kotlin.math.abs

/**
 * Android-версия должна выдавать то же самое, что компьютерная PGL Mocap.
 * fixture.json сделан компьютерной версией (tests/make_android_fixture.py).
 */
class MatchDesktopTest {
    private val cases: JSONArray by lazy {
        val text = javaClass.classLoader!!.getResource("fixture.json")!!.readText()
        JSONObject(text).getJSONArray("cases")
    }

    private fun mat(a: JSONArray) = Array(a.length()) { i ->
        val r = a.getJSONArray(i); DoubleArray(r.length()) { r.getDouble(it) }
    }

    private fun vec(a: JSONArray) = DoubleArray(a.length()) { a.getDouble(it) }

    private fun assertClose(exp: DoubleArray, act: DoubleArray, tol: Double, what: String) {
        assertEquals("$what: размер", exp.size, act.size)
        for (i in exp.indices) assertTrue("$what[$i]: ожидалось ${exp[i]}, получено ${act[i]}", abs(exp[i] - act[i]) <= tol)
    }

    private fun pose(c: JSONObject) = Pose(mat(c.getJSONArray("norm")), mat(c.getJSONArray("world")), vec(c.getJSONArray("vis")))

    @Test
    fun liveLinkPointsAndBones() {
        for (k in 0 until cases.length()) {
            val c = cases.getJSONObject(k)
            val (root, pts) = LiveLinkFormat.computePoints(pose(c), c.getDouble("aspect"), 200.0)
            assertClose(vec(c.getJSONArray("ll_root")), root, 1e-6, "root#$k")
            val expPts = mat(c.getJSONArray("ll_points"))
            for (i in expPts.indices) assertClose(expPts[i], pts[i], 1e-6, "point#$k/$i")

            val (bones, _) = LiveLinkFormat.computeBones(pts)
            val expBones = mat(c.getJSONArray("ll_bones"))
            assertEquals(expBones.size, bones.size)
            for (i in expBones.indices) {
                val e = expBones[i]
                val a = bones[i]
                assertClose(e.copyOfRange(0, 3), a.copyOfRange(0, 3), 1e-6, "bone#$k/${LiveLinkFormat.BONE_NAMES[i]} t")
                // q и -q — один и тот же поворот
                val dot = (0..3).sumOf { e[3 + it] * a[3 + it] }
                assertTrue("bone#$k/${LiveLinkFormat.BONE_NAMES[i]} q: dot=$dot", abs(abs(dot) - 1.0) < 1e-6)
            }
        }
    }

    @Test
    fun oscCoordinates() {
        for (k in 0 until cases.length()) {
            val c = cases.getJSONObject(k)
            val p = pose(c)
            val aspect = c.getDouble("aspect")
            val screen = OscFormat.transform(OscFormat.screenCoords(p.norm, aspect), Settings())
            val expS = mat(c.getJSONArray("osc_screen"))
            for (i in expS.indices) assertClose(expS[i], screen[i], 1e-9, "screen#$k/$i")

            val s = Settings(coordMode = "world", upAxis = "z", scale = 2.0, flipX = true, offsetX = 1.0, offsetY = -2.0, offsetZ = 0.5)
            val world = OscFormat.transform(OscFormat.worldCoords(p.world), s)
            val expW = mat(c.getJSONArray("osc_world_z"))
            for (i in expW.indices) assertClose(expW[i], world[i], 1e-9, "world#$k/$i")
        }
    }

    @Test
    fun oscMessageEncoding() {
        // /a ,fff 1 2 3 — проверка байтов по спецификации OSC 1.0
        val b = OscMessage("/pglmocap/p1/nose", floatArrayOf(1f, -2.5f, 0.25f)).encode()
        val addr = "/pglmocap/p1/nose".toByteArray()
        val addrLen = (addr.size / 4 + 1) * 4
        assertEquals(0, b.size % 4)
        assertEquals("/pglmocap/p1/nose", String(b, 0, addr.size))
        assertEquals(0.toByte(), b[addr.size])
        assertEquals(",fff", String(b, addrLen, 4))
        val bb = ByteBuffer.wrap(b, addrLen + 8, 12)
        assertEquals(1f, bb.float, 0f)
        assertEquals(-2.5f, bb.float, 0f)
        assertEquals(0.25f, bb.float, 0f)
        assertEquals(addrLen + 8 + 12, b.size)
    }

    @Test
    fun oscFrameAddresses() {
        val p = pose(cases.getJSONObject(0))
        val msgs = OscFormat.buildFrame(listOf(p, null), 16.0 / 9, Settings(), 2)
        val addrs = msgs.map { it.address }
        assertEquals("/pglmocap/count", addrs[0])
        assertTrue("/pglmocap/p1/detected" in addrs)
        assertTrue("/pglmocap/p1/right_wrist" in addrs)
        assertTrue("/pglmocap/p1/hip_center" in addrs)
        assertTrue("/pglmocap/p1/screen_pos" in addrs)
        assertTrue("/pglmocap/p2/detected" in addrs)
        // 1 count + p1 (detected + 33 + 3 центра) + p2 detected — как у компьютерной версии
        assertEquals(1 + 1 + 33 + 3 + 1, msgs.size)
    }

    @Test
    fun liveLinkPacket() {
        val p = pose(cases.getJSONObject(0))
        val packer = LiveLinkFormat.Packer()
        val pkt = JSONObject(packer.build(listOf(p, null), 16.0 / 9, Settings(llEnabled = true)))
        assertEquals(1, pkt.getInt("v"))
        assertEquals("PGL", pkt.getString("prefix"))
        val person = pkt.getJSONArray("persons").getJSONObject(0)
        assertEquals(1, person.getInt("id"))
        assertEquals(35, person.getJSONObject("points").length())
        assertEquals(17, person.getJSONArray("bones").length())
        assertEquals(17, person.getJSONArray("names").length())
        val pkt2 = JSONObject(packer.build(listOf(null, null), 16.0 / 9, Settings(llEnabled = true)))
        assertEquals(0, pkt2.getJSONArray("persons").length())
        assertEquals(1, pkt2.getJSONArray("lost").getInt(0))
    }

    @Test
    fun smoothingAndHold() {
        val base = pose(cases.getJSONObject(0))
        val slots = PoseSlots(2)
        val s = Settings(smoothing = 0.7, holdSeconds = 0.3)
        val rnd = java.util.Random(1)
        val xs = ArrayList<Double>()
        var t = 0.0
        repeat(30) {
            t += 1.0 / 30
            val q = base.copy()
            for (r in q.norm) { r[0] += rnd.nextGaussian() * 0.01; r[1] += rnd.nextGaussian() * 0.01 }
            xs.add(slots.assign(listOf(q), t, s)[0]!!.norm[IDX.getValue("right_wrist")][0])
        }
        val tail = xs.drop(10)
        val mean = tail.average()
        val std = kotlin.math.sqrt(tail.sumOf { (it - mean) * (it - mean) } / tail.size)
        assertTrue("сглаживание: std=$std", std < 0.007)
        assertTrue(slots.assign(emptyList(), t + 0.1, s)[0] != null)   // удержание
        assertTrue(slots.assign(emptyList(), t + 0.5, s)[0] == null)   // потеря
    }
}
