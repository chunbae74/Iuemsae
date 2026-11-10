package kr.ieumsae.app.tts

import org.junit.Assert.*
import org.junit.Test

class AudioPlaybackTest {
    @Test fun audioRemainsAvailableUntilPlaybackEnds() {
        val audio = byteArrayOf(1, 2, 3)
        var releases = 0
        val owner = AudioPlayback(Any(), audio) { releases++ }
        assertFalse(owner.closed)
        assertArrayEquals(byteArrayOf(1, 2, 3), audio)
        owner.close()
        assertTrue(owner.closed)
        assertEquals(1, releases)
        assertArrayEquals(ByteArray(3), audio)
    }

    @Test fun repeatedStopAndLateCallbacksDoNotReleaseTwice() {
        var releases = 0
        val owner = AudioPlayback(Any(), byteArrayOf(4)) { releases++ }
        repeat(3) { owner.close() }
        assertEquals(1, releases)
    }

    @Test fun nativeReleaseFailureStillWipesAudioAndEndsOwnership() {
        val audio = byteArrayOf(8, 9)
        val failure = IllegalStateException("native release failed")
        val owner = AudioPlayback(Any(), audio) { throw failure }
        try {
            owner.close()
            fail("failure must propagate")
        } catch (actual: IllegalStateException) {
            assertSame(failure, actual)
        }
        assertTrue(owner.closed)
        assertArrayEquals(ByteArray(2), audio)
        owner.close()
    }
}
