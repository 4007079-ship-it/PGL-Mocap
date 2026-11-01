package com.pgl.mocap

import kotlin.math.sqrt

/** Мини-набор операций над 3D-векторами (DoubleArray из 3 элементов) и матрицами 3x3 (по столбцам). */
object V {
    fun of(x: Double, y: Double, z: Double) = doubleArrayOf(x, y, z)
    fun add(a: DoubleArray, b: DoubleArray) = doubleArrayOf(a[0] + b[0], a[1] + b[1], a[2] + b[2])
    fun sub(a: DoubleArray, b: DoubleArray) = doubleArrayOf(a[0] - b[0], a[1] - b[1], a[2] - b[2])
    fun mul(a: DoubleArray, s: Double) = doubleArrayOf(a[0] * s, a[1] * s, a[2] * s)
    fun mid(a: DoubleArray, b: DoubleArray) = doubleArrayOf((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
    fun dot(a: DoubleArray, b: DoubleArray) = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    fun cross(a: DoubleArray, b: DoubleArray) = doubleArrayOf(
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )
    fun len(a: DoubleArray) = sqrt(dot(a, a))
    fun norm(a: DoubleArray): DoubleArray? {
        val n = len(a)
        return if (n > 1e-9) mul(a, 1.0 / n) else null
    }
}

/** Матрица поворота 3x3; m[r][c]. Столбцы — оси X, Y, Z. */
class Mat3(val m: Array<DoubleArray>) {
    fun col(c: Int) = doubleArrayOf(m[0][c], m[1][c], m[2][c])

    fun transpose() = Mat3(Array(3) { r -> DoubleArray(3) { c -> m[c][r] } })

    fun times(v: DoubleArray) = DoubleArray(3) { r -> m[r][0] * v[0] + m[r][1] * v[1] + m[r][2] * v[2] }

    fun times(o: Mat3) = Mat3(Array(3) { r -> DoubleArray(3) { c -> m[r][0] * o.m[0][c] + m[r][1] * o.m[1][c] + m[r][2] * o.m[2][c] } })

    /** -> кватернион (x, y, z, w), w >= 0 */
    fun toQuat(): DoubleArray {
        val t = m[0][0] + m[1][1] + m[2][2]
        val q: DoubleArray
        if (t > 0) {
            val s = sqrt(t + 1.0) * 2
            q = doubleArrayOf((m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, 0.25 * s)
        } else if (m[0][0] > m[1][1] && m[0][0] > m[2][2]) {
            val s = sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
            q = doubleArrayOf(0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s)
        } else if (m[1][1] > m[2][2]) {
            val s = sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
            q = doubleArrayOf((m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s)
        } else {
            val s = sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
            q = doubleArrayOf((m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s, (m[1][0] - m[0][1]) / s)
        }
        val n = sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
        for (i in 0..3) q[i] /= n
        if (q[3] < 0) for (i in 0..3) q[i] = -q[i]
        return q
    }

    companion object {
        val IDENTITY = Mat3(arrayOf(doubleArrayOf(1.0, 0.0, 0.0), doubleArrayOf(0.0, 1.0, 0.0), doubleArrayOf(0.0, 0.0, 1.0)))

        fun fromColumns(x: DoubleArray, y: DoubleArray, z: DoubleArray) =
            Mat3(arrayOf(doubleArrayOf(x[0], y[0], z[0]), doubleArrayOf(x[1], y[1], z[1]), doubleArrayOf(x[2], y[2], z[2])))
    }
}
