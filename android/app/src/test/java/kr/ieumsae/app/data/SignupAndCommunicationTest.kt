package kr.ieumsae.app.data

import org.junit.Assert.*
import org.junit.Test

class SignupAndCommunicationTest {
    private fun valid(password: String, id: String = "tester") = PasswordRules.evaluate(password, id).all { it.met }

    @Test fun passwordBoundaries() {
        assertTrue(valid("Abcdef12"))
        assertFalse(valid("Abcde12"))
        assertTrue(valid("abcdef1234"))
        assertFalse(valid("abcdef123"))
        assertFalse(valid("abcdefghij"))
        assertFalse(valid("Abcccc12"))
        assertFalse(valid("Tester12!"))
        assertTrue(valid("Ab1!".repeat(16)))
        assertFalse(valid("Ab1!".repeat(16) + "x"))
        assertFalse(valid(""))
        assertTrue(valid("abcd123😀😀😀"))
        assertFalse(valid("abcd123😀😀😀😀"))
    }

    @Test fun onlyComprehensionIsShared() {
        assertNull(CommunicationText.forListener(null))
        assertNull(CommunicationText.forListener(Communication(speechLevel = 3)))
        assertNull(CommunicationText.forListener(Communication(3, 3, false)))
        assertEquals("쉬운 말로 천천히 설명해 주세요", CommunicationText.forListener(Communication(3, 3, true)))
        assertEquals("편하게 말씀해주세요", CommunicationText.forListener(Communication(1, 1, true)))
        assertEquals("천천히 말해 주세요", CommunicationText.forListener(Communication(null, 2, true)))
    }
}
