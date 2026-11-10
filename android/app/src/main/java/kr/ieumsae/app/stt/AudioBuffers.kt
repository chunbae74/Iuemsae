package kr.ieumsae.app.stt

import kotlinx.coroutines.channels.Channel

internal fun audioQueue(): Channel<ByteArray> =
    Channel(Channel.UNLIMITED, onUndeliveredElement = { it.fill(0) })

internal fun Channel<ByteArray>.enqueueAudio(buffer: ByteArray): Boolean {
    val accepted = trySend(buffer).isSuccess
    if (!accepted) buffer.fill(0)
    return accepted
}
