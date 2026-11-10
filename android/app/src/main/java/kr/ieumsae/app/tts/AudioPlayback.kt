package kr.ieumsae.app.tts

internal class AudioPlayback<T>(
    val player: T,
    private val audio: ByteArray,
    private val releasePlayer: (T) -> Unit,
) : AutoCloseable {
    var closed = false
        private set

    override fun close() {
        if (closed) return
        closed = true
        try {
            releasePlayer(player)
        } finally {
            audio.fill(0)
        }
    }
}
