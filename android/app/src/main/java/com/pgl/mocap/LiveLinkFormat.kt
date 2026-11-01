package com.pgl.mocap

import org.json.JSONArray
import org.json.JSONObject

/**
 * Пакет для плагина PGL Mocap Live Link (Unreal Engine) — тот же формат и та же математика,
 * что у компьютерной версии (pglmocap/livelink_output.py).
 * Координаты Unreal: сантиметры, X вперёд, Y вправо, Z вверх, пол Z = 0.
 */
object LiveLinkFormat {
    val BONE_NAMES = listOf(
        "root", "pelvis", "spine_01", "neck_01", "head",
        "upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r",
        "thigh_l", "calf_l", "foot_l", "thigh_r", "calf_r", "foot_r",
    )
    val BONE_PARENTS = listOf(-1, 0, 1, 2, 3, 2, 5, 6, 2, 8, 9, 1, 11, 12, 1, 14, 15)

    private val FLOOR_POINTS = listOf("left_ankle", "right_ankle", "left_heel", "right_heel",
        "left_foot_index", "right_foot_index").map { IDX.getValue(it) }

    /** Базис со столбцами X, Y, Z: X вдоль xDir, Z как можно ближе к zHint. */
    fun basis(xDir: DoubleArray, zHint: DoubleArray?, fallback: DoubleArray?): Mat3 {
        val x = V.norm(xDir) ?: return Mat3.IDENTITY
        var z: DoubleArray? = null
        for (hint in listOf(zHint, fallback, V.of(0.0, 0.0, 1.0), V.of(0.0, 1.0, 0.0))) {
            if (hint == null) continue
            z = V.norm(V.sub(hint, V.mul(x, V.dot(hint, x))))
            if (z != null) break
        }
        val zz = z ?: return Mat3.IDENTITY
        val y = V.cross(zz, x)
        return Mat3.fromColumns(x, y, zz)
    }

    fun mediapipeWorldToUe(world: Array<DoubleArray>) = Array(world.size) { i ->
        doubleArrayOf(-world[i][2] * 100.0, -world[i][0] * 100.0, -world[i][1] * 100.0)
    }

    /** -> (root, points) в см Unreal; точки относительно root, пол на Z = 0. */
    fun computePoints(pose: Pose, aspect: Double, rootMotion: Double): Pair<DoubleArray, Array<DoubleArray>> {
        val pts = mediapipeWorldToUe(pose.world)
        val floor = FLOOR_POINTS.minOf { pts[it][2] }
        for (p in pts) p[2] -= floor
        val root = DoubleArray(3)
        if (rootMotion != 0.0) {
            val hipX = pose.hipCenterNorm()[0]
            root[1] = -(hipX - 0.5) * aspect * rootMotion
        }
        return Pair(root, pts)
    }

    /** Локальные трансформы костей [tx,ty,tz,qx,qy,qz,qw] и компонентные (позиция, поворот). */
    fun computeBones(pts: Array<DoubleArray>): Pair<List<DoubleArray>, List<Pair<DoubleArray, Mat3>>> {
        fun P(n: String) = pts[IDX.getValue(n)]
        val hipC = V.mid(P("left_hip"), P("right_hip"))
        val shC = V.mid(P("left_shoulder"), P("right_shoulder"))
        val earC = V.mid(P("left_ear"), P("right_ear"))
        val rightHips = V.sub(P("right_hip"), P("left_hip"))
        val rightSh = V.sub(P("right_shoulder"), P("left_shoulder"))
        val up = V.sub(shC, hipC)
        val fwd = V.norm(V.cross(rightHips, up)) ?: V.of(1.0, 0.0, 0.0)

        fun limb(a: DoubleArray, b: DoubleArray, c: DoubleArray, fb: DoubleArray): Mat3 {
            val n = V.cross(V.sub(b, a), V.sub(c, b))
            return basis(V.sub(b, a), if (V.len(n) > 1e-3) n else null, fb)
        }

        val handMidL = V.mid(P("left_index"), P("left_pinky"))
        val handMidR = V.mid(P("right_index"), P("right_pinky"))

        val comp = ArrayList<Pair<DoubleArray, Mat3>>(BONE_NAMES.size)
        comp.add(Pair(DoubleArray(3), Mat3.IDENTITY))                                              // root
        comp.add(Pair(hipC, basis(up, rightHips, rightSh)))                                         // pelvis
        comp.add(Pair(hipC, basis(up, rightSh, rightHips)))                                         // spine_01
        comp.add(Pair(shC, basis(V.sub(earC, shC), rightSh, rightHips)))                            // neck_01
        comp.add(Pair(earC, basis(V.sub(earC, shC), V.sub(P("right_ear"), P("left_ear")), rightSh))) // head
        val ual = limb(P("left_shoulder"), P("left_elbow"), P("left_wrist"), fwd)
        comp.add(Pair(P("left_shoulder"), ual))                                                     // upperarm_l
        comp.add(Pair(P("left_elbow"), basis(V.sub(P("left_wrist"), P("left_elbow")), ual.col(2), fwd)))
        comp.add(Pair(P("left_wrist"), basis(V.sub(handMidL, P("left_wrist")), V.sub(P("left_index"), P("left_pinky")), fwd)))
        val uar = limb(P("right_shoulder"), P("right_elbow"), P("right_wrist"), fwd)
        comp.add(Pair(P("right_shoulder"), uar))                                                    // upperarm_r
        comp.add(Pair(P("right_elbow"), basis(V.sub(P("right_wrist"), P("right_elbow")), uar.col(2), fwd)))
        comp.add(Pair(P("right_wrist"), basis(V.sub(handMidR, P("right_wrist")), V.sub(P("right_index"), P("right_pinky")), fwd)))
        val thl = limb(P("left_hip"), P("left_knee"), P("left_ankle"), rightHips)
        comp.add(Pair(P("left_hip"), thl))                                                          // thigh_l
        comp.add(Pair(P("left_knee"), basis(V.sub(P("left_ankle"), P("left_knee")), thl.col(2), rightHips)))
        comp.add(Pair(P("left_ankle"), basis(V.sub(P("left_foot_index"), P("left_ankle")), rightHips, null)))
        val thr = limb(P("right_hip"), P("right_knee"), P("right_ankle"), rightHips)
        comp.add(Pair(P("right_hip"), thr))                                                         // thigh_r
        comp.add(Pair(P("right_knee"), basis(V.sub(P("right_ankle"), P("right_knee")), thr.col(2), rightHips)))
        comp.add(Pair(P("right_ankle"), basis(V.sub(P("right_foot_index"), P("right_ankle")), rightHips, null)))

        val local = comp.mapIndexed { i, (pos, rot) ->
            val p = BONE_PARENTS[i]
            val t: DoubleArray
            val r: Mat3
            if (p < 0) {
                t = pos; r = rot
            } else {
                val (ppos, prot) = comp[p]
                val pt = prot.transpose()
                t = pt.times(V.sub(pos, ppos))
                r = pt.times(rot)
            }
            val q = r.toQuat()
            doubleArrayOf(t[0], t[1], t[2], q[0], q[1], q[2], q[3])
        }
        return Pair(local, comp)
    }

    private fun arr(v: DoubleArray, digits: Int): JSONArray {
        val a = JSONArray()
        for (x in v) a.put(round(x, digits))
        return a
    }

    private fun round(x: Double, digits: Int): Double {
        var m = 1.0
        repeat(digits) { m *= 10 }
        return Math.round(x * m) / m
    }

    /** Состояние между кадрами — чтобы сообщать о пропавших людях. */
    class Packer {
        private var seen = setOf<Int>()

        fun build(poses: List<Pose?>, aspect: Double, s: Settings): String {
            val names = if (s.llPoints == "all") LANDMARK_NAMES else CORE_JOINTS
            val persons = JSONArray()
            val now = HashSet<Int>()
            poses.forEachIndexed { slot, pose ->
                if (pose == null) return@forEachIndexed
                val pid = slot + 1
                now.add(pid)
                val (root, pts) = computePoints(pose, aspect, s.llRootMotion)
                val points = JSONObject()
                for (n in names) points.put(n, arr(pts[IDX.getValue(n)], 3))
                points.put("hip_center", arr(V.mid(pts[IDX.getValue("left_hip")], pts[IDX.getValue("right_hip")]), 3))
                points.put("shoulder_center", arr(V.mid(pts[IDX.getValue("left_shoulder")], pts[IDX.getValue("right_shoulder")]), 3))
                val (bones, _) = computeBones(pts)
                bones[0][0] = root[0]; bones[0][1] = root[1]; bones[0][2] = root[2]
                val bonesJson = JSONArray()
                for (b in bones) bonesJson.put(arr(b, 5))
                persons.put(JSONObject()
                    .put("id", pid)
                    .put("root", arr(root, 3))
                    .put("points", points)
                    .put("names", JSONArray(BONE_NAMES))
                    .put("parents", JSONArray(BONE_PARENTS))
                    .put("bones", bonesJson))
            }
            val lost = JSONArray((seen - now).sorted())
            seen = now
            return JSONObject()
                .put("v", 1)
                .put("prefix", s.llPrefix.ifBlank { "PGL" })
                .put("persons", persons)
                .put("lost", lost)
                .toString()
        }
    }
}
