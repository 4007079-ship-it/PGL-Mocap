package com.pgl.mocap

/** 33 точки MediaPipe Pose — те же имена, что в компьютерной версии PGL Mocap. */
val LANDMARK_NAMES = listOf(
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
)
val IDX: Map<String, Int> = LANDMARK_NAMES.withIndex().associate { it.value to it.index }

val CORE_JOINTS = listOf(
    "nose", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)

/** Линии скелета для отрисовки. */
val SKELETON = listOf(
    11 to 12, 11 to 13, 13 to 15, 12 to 14, 14 to 16,
    11 to 23, 12 to 24, 23 to 24, 23 to 25, 25 to 27, 24 to 26, 26 to 28,
    27 to 29, 29 to 31, 27 to 31, 28 to 30, 30 to 32, 28 to 32,
    15 to 17, 15 to 19, 15 to 21, 16 to 18, 16 to 20, 16 to 22,
    0 to 2, 0 to 5, 2 to 7, 5 to 8, 9 to 10,
)

/**
 * Одна поза.
 * norm  — x, y в долях кадра (0..1), z — относительная глубина (как в MediaPipe)
 * world — метры, центр между бёдрами, y вниз, z от камеры (как в MediaPipe)
 * vis   — видимость 0..1
 */
class Pose(val norm: Array<DoubleArray>, val world: Array<DoubleArray>, val vis: DoubleArray) {
    fun copy() = Pose(norm.map { it.clone() }.toTypedArray(), world.map { it.clone() }.toTypedArray(), vis.clone())

    fun hipCenterNorm(): DoubleArray {
        val l = norm[IDX.getValue("left_hip")]
        val r = norm[IDX.getValue("right_hip")]
        return doubleArrayOf((l[0] + r[0]) / 2, (l[1] + r[1]) / 2)
    }
}
