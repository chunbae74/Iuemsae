package kr.ieumsae.app.stt

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import kr.ieumsae.app.security.SttCrypto
import org.junit.Assert.*
import org.junit.Test

class SensitiveAudioLifecycleTest {
    @Test fun setupTransfersAUsableKeyOnlyOnSuccess() = runBlocking {
        val bytes = ByteArray(32) { 7 }
        val key = SttCrypto.SessionKey(bytes)
        assertEquals("ready", key.transferAfter { "ready" })
        assertTrue(bytes.all { it == 7.toByte() })
        key.wipe()
        assertTrue(bytes.all { it == 0.toByte() })
    }

    @Test fun setupFailuresAndCancellationWipeTheUntransferredKey() = runBlocking {
        for (failure in listOf(IllegalArgumentException("seal"), IllegalStateException("upload"), CancellationException("cancelled"))) {
            val bytes = ByteArray(32) { 9 }
            val key = SttCrypto.SessionKey(bytes)
            try {
                key.transferAfter { throw failure }
                fail("setup must fail")
            } catch (actual: Exception) {
                assertSame(failure, actual)
            }
            assertTrue(bytes.all { it == 0.toByte() })
        }
    }

    @Test fun cancellationWipesEveryQueuedAudioChunk() {
        val queue = audioQueue()
        val chunks = List(3) { ByteArray(640) { 12 } }
        chunks.forEach { assertTrue(queue.enqueueAudio(it)) }
        queue.cancel()
        assertTrue(chunks.all { chunk -> chunk.all { it == 0.toByte() } })
    }

    @Test fun rejectedChunksAreWipedButDeliveredAudioRemainsUsable() = runBlocking {
        val queue = audioQueue()
        val delivered = byteArrayOf(1, 2, 3)
        assertTrue(queue.enqueueAudio(delivered))
        assertSame(delivered, queue.receive())
        assertArrayEquals(byteArrayOf(1, 2, 3), delivered)
        queue.close()
        val rejected = byteArrayOf(4, 5, 6)
        assertFalse(queue.enqueueAudio(rejected))
        assertArrayEquals(ByteArray(3), rejected)
    }
}
