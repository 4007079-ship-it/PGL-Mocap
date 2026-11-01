package com.pgl.mocap

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.hypot

/** One Euro Filter по массиву значений (как в компьютерной версии). */
class OneEuro(var minCutoff: Double = 1.0, var beta: Double = 0.02, private val dCutoff: Double = 1.0) {
    private var xPrev: DoubleArray? = null
    private var dxPrev: DoubleArray? = null
    private var tPrev = 0.0

    fun reset() {
        xPrev = null
        dxPrev = null
    }

    private fun alpha(cutoff: Double, dt: Double): Double {
        val tau = 1.0 / (2 * PI * cutoff)
        return 1.0 / (1.0 + tau / dt)
    }

    fun filter(x: DoubleArray, t: Double): DoubleArray {
        val xp = xPrev
        if (xp == null || xp.size != x.size) {
            xPrev = x.clone()
            dxPrev = DoubleArray(x.size)
            tPrev = t
            return x.clone()
        }
        val dt = maxOf(t - tPrev, 1e-4)
        tPrev = t
        val dxp = dxPrev!!
        val aD = alpha(dCutoff, dt)
        val out = DoubleArray(x.size)
        for (i in x.indices) {
            val dx = (x[i] - xp[i]) / dt
            val dxHat = aD * dx + (1 - aD) * dxp[i]
            val cutoff = minCutoff + beta * abs(dxHat)
            val a = alpha(cutoff, dt)
            out[i] = a * x[i] + (1 - a) * xp[i]
            dxp[i] = dxHat
        }
        xPrev = out.clone()
        return out
    }

    companion object {
        /** Ползунок 0..1 -> (minCutoff, beta). */
        fun paramsFromStrength(strength: Double): Pair<Double, Double> {
            val s = strength.coerceIn(0.0, 1.0)
            return Pair(8.0 * (1 - s) + 0.4 * s, 0.5 * (1 - s) + 0.01 * s)
        }
    }
}

private fun flatten(a: Array<DoubleArray>) = DoubleArray(a.size * 3) { a[it / 3][it % 3] }
private fun unflatten(f: DoubleArray) = Array(f.size / 3) { i -> doubleArrayOf(f[i * 3], f[i * 3 + 1], f[i * 3 + 2]) }

/**
 * Стабильная нумерация людей (P1..P4), сглаживание и удержание позы при кратковременной потере.
 * Логика повторяет engine._assign компьютерной версии.
 */
class PoseSlots(n: Int) {
    private class Slot {
        val fNorm = OneEuro()
        val fWorld = OneEuro()
        val fVis = OneEuro()
        var pose: Pose? = null
        var lastSeen = 0.0
    }

    private val slots = List(n) { Slot() }

    fun assign(poses: List<Pose>, now: Double, s: Settings): List<Pose?> {
        val (mc, beta) = OneEuro.paramsFromStrength(s.smoothing)
        data class Cand(val d: Double, val p: Int, val s: Int)

        val cands = ArrayList<Cand>()
        for ((pi, p) in poses.withIndex()) {
            val c = p.hipCenterNorm()
            for ((si, slot) in slots.withIndex()) {
                val sc = slot.pose?.hipCenterNorm()
                val d = if (sc == null) 0.5 else hypot(c[0] - sc[0], c[1] - sc[1])
                cands.add(Cand(d, pi, si))
            }
        }
        cands.sortBy { it.d }
        val usedP = HashSet<Int>()
        val assigned = HashMap<Int, Int>()   // slot -> pose
        for (c in cands) {
            if (c.p in usedP || c.s in assigned) continue
            usedP.add(c.p)
            assigned[c.s] = c.p
        }

        return slots.mapIndexed { si, slot ->
            for (f in listOf(slot.fNorm, slot.fWorld, slot.fVis)) {
                f.minCutoff = mc
                f.beta = beta
            }
            val pi = assigned[si]
            if (pi != null) {
                var p = poses[pi]
                if (slot.pose == null) {
                    slot.fNorm.reset(); slot.fWorld.reset(); slot.fVis.reset()
                }
                if (s.smoothing > 0.001) {
                    p = Pose(
                        unflatten(slot.fNorm.filter(flatten(p.norm), now)),
                        unflatten(slot.fWorld.filter(flatten(p.world), now)),
                        slot.fVis.filter(p.vis, now),
                    )
                }
                slot.pose = p
                slot.lastSeen = now
                p
            } else if (slot.pose != null && now - slot.lastSeen <= s.holdSeconds) {
                slot.pose
            } else {
                slot.pose = null
                null
            }
        }
    }
}
