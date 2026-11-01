package com.pgl.mocap

import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/** Отправка OSC и Live Link по UDP. Вызывается из потока анализа (не из UI-потока). */
class Sender {
    private val socket = DatagramSocket()
    private val packer = LiveLinkFormat.Packer()
    private var cachedHost: String? = null
    private var cachedAddr: InetAddress? = null

    var oscMessages = 0L
        private set
    var llPackets = 0L
        private set
    @Volatile var lastError: String? = null
        private set

    private fun addr(host: String): InetAddress {
        if (host != cachedHost || cachedAddr == null) {
            cachedAddr = InetAddress.getByName(host.trim())
            cachedHost = host
        }
        return cachedAddr!!
    }

    fun send(poses: List<Pose?>, aspect: Double, s: Settings) {
        try {
            if (s.oscEnabled || s.llEnabled) {
                val a = addr(s.targetIp)
                if (s.oscEnabled) {
                    for (m in OscFormat.buildFrame(poses, aspect, s, s.numPoses)) {
                        val b = m.encode()
                        socket.send(DatagramPacket(b, b.size, a, s.oscPort))
                        oscMessages++
                    }
                }
                if (s.llEnabled) {
                    val b = packer.build(poses, aspect, s).toByteArray(Charsets.UTF_8)
                    socket.send(DatagramPacket(b, b.size, a, s.llPort))
                    llPackets++
                }
            }
            lastError = null
        } catch (e: Exception) {
            lastError = e.message ?: e.javaClass.simpleName
        }
    }

    fun close() = socket.close()
}
