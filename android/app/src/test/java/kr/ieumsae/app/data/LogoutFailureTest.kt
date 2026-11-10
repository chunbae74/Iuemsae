package kr.ieumsae.app.data

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class LogoutFailureTest {
    @Test fun successfulRevocationClearsLocalTokens() = runBlocking {
        val events = mutableListOf<String>()
        assertTrue(revokeAndClear({ events += "revoked" }, { events += "cleared" }))
        assertEquals(listOf("revoked", "cleared"), events)
    }

    @Test fun failedRequestsClearLocallyWithoutClaimingServerRevocation() = runBlocking {
        for (status in listOf(0, 503)) {
            var clears = 0
            assertFalse(revokeAndClear({ throw ApiException(status, "failure") }, { clears++ }))
            assertEquals(1, clears)
        }
    }

    @Test fun cancellationAndUnexpectedFailuresPropagateAfterLocalCleanup() = runBlocking {
        for (failure in listOf(CancellationException("cancelled"), IllegalStateException("unexpected"))) {
            var clears = 0
            try {
                revokeAndClear({ throw failure }, { clears++ })
                fail("failure must propagate")
            } catch (actual: Exception) {
                assertSame(failure, actual)
            }
            assertEquals(1, clears)
        }
    }
}
