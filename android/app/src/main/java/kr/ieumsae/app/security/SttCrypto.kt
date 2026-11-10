package kr.ieumsae.app.security

import android.util.Base64
import com.google.crypto.tink.HybridEncrypt
import com.google.crypto.tink.KeysetHandle
import com.google.crypto.tink.RegistryConfiguration
import com.google.crypto.tink.hybrid.HpkeParameters
import com.google.crypto.tink.hybrid.HpkePublicKey
import com.google.crypto.tink.hybrid.HybridConfig
import com.google.crypto.tink.util.Bytes
import kr.ieumsae.app.BuildConfig
import java.security.KeyFactory
import java.security.SecureRandom
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.util.Arrays
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec


object SttCrypto {
    const val SESSION_SIG_VERSION = "IEUMSAE-STT-SESSION-V1"
    const val TTS_SESSION_SIG_VERSION = "IEUMSAE-TTS-SESSION-V1"
    private val HPKE_INFO_PREFIX = "ieumsae-stt-v1|".toByteArray()
    private val TTS_HPKE_INFO_PREFIX = "ieumsae-tts-v1|".toByteArray()
    private val random = SecureRandom()


    private const val ENC_LEN = 65

    init {
        HybridConfig.register()
    }

    class SessionKey(private val key: ByteArray) {
        fun bytes(): ByteArray = key


        fun wipe() = Arrays.fill(key, 0)

        internal suspend fun <T> transferAfter(prepare: suspend () -> T): T {
            var transferred = false
            try {
                val result = prepare()
                transferred = true
                return result
            } finally {
                if (!transferred) wipe()
            }
        }
    }

    class Sealed(val enc: String, val ciphertext: String)
    class Encrypted(val iv: String, val ciphertext: String)

    fun verifySession(
        sessionId: String,
        hpkePublicKey: String,
        serverKeyId: String,
        expiresAt: Long,
        userId: String,
        deviceId: String,
        signature: String,
        version: String = SESSION_SIG_VERSION,
    ): Boolean {
        if (serverKeyId != BuildConfig.STT_SIGNING_KEY_ID || BuildConfig.STT_SIGNING_PUBLIC_KEY.isEmpty()) return false
        if (expiresAt < System.currentTimeMillis()) return false
        val pub = KeyFactory.getInstance("EC")
            .generatePublic(X509EncodedKeySpec(Base64.decode(BuildConfig.STT_SIGNING_PUBLIC_KEY, Base64.NO_WRAP)))
        val msg = listOf(version, sessionId, hpkePublicKey, serverKeyId, expiresAt.toString(), userId, deviceId)
            .joinToString("\n")
        return runCatching {
            Signature.getInstance("SHA256withECDSA").run {
                initVerify(pub)
                update(msg.toByteArray())
                verify(Base64.decode(signature, Base64.NO_WRAP))
            }
        }.getOrDefault(false)
    }

    fun newSessionKey(): SessionKey = SessionKey(ByteArray(32).also { random.nextBytes(it) })

    fun sealSessionKey(sessionId: String, hpkePublicKeyB64: String, key: SessionKey): Sealed =
        seal(HPKE_INFO_PREFIX + sessionId.toByteArray(), hpkePublicKeyB64, key.bytes())


    fun sealTtsRequest(sessionId: String, hpkePublicKeyB64: String, payload: ByteArray): Sealed =
        seal(TTS_HPKE_INFO_PREFIX + sessionId.toByteArray(), hpkePublicKeyB64, payload)

    fun decryptTtsAudio(key: SessionKey, sessionId: String, iv: String, ciphertext: String): ByteArray =
        aesDecrypt(key, iv, ciphertext, "$sessionId|tts".toByteArray())

    private fun seal(info: ByteArray, hpkePublicKeyB64: String, plaintext: ByteArray): Sealed {
        val params = HpkeParameters.builder()
            .setVariant(HpkeParameters.Variant.NO_PREFIX)
            .setKemId(HpkeParameters.KemId.DHKEM_P256_HKDF_SHA256)
            .setKdfId(HpkeParameters.KdfId.HKDF_SHA256)
            .setAeadId(HpkeParameters.AeadId.AES_256_GCM)
            .build()
        val raw = Base64.decode(hpkePublicKeyB64, Base64.NO_WRAP)
        require(raw.size == ENC_LEN && raw[0] == 0x04.toByte()) { "세션 공개키 길이 오류" }
        val publicKey = HpkePublicKey.create(params, Bytes.copyFrom(raw), null)
        val handle = KeysetHandle.newBuilder()
            .addEntry(KeysetHandle.importKey(publicKey).withRandomId().makePrimary())
            .build()
        val hybrid = handle.getPrimitive(RegistryConfiguration.get(), HybridEncrypt::class.java)

        val out = hybrid.encrypt(plaintext, info)
        return Sealed(
            enc = b64(out.copyOfRange(0, ENC_LEN)),
            ciphertext = b64(out.copyOfRange(ENC_LEN, out.size)),
        )
    }

    fun encryptChunk(key: SessionKey, sessionId: String, seq: Int, timestamp: Long, pcm: ByteArray, len: Int): Encrypted =
        encrypt(key, pcm, len, "$sessionId|chunk|$seq|$timestamp".toByteArray())

    fun decryptResult(key: SessionKey, sessionId: String, iv: String, ciphertext: String): ByteArray =
        aesDecrypt(key, iv, ciphertext, "$sessionId|result".toByteArray())

    private fun aesDecrypt(key: SessionKey, iv: String, ciphertext: String, aad: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(
            Cipher.DECRYPT_MODE,
            SecretKeySpec(key.bytes(), "AES"),
            GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)),
        )
        cipher.updateAAD(aad)
        return cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP))
    }

    private fun encrypt(key: SessionKey, data: ByteArray, len: Int, aad: ByteArray): Encrypted {
        val iv = ByteArray(12).also { random.nextBytes(it) }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key.bytes(), "AES"), GCMParameterSpec(128, iv))
        cipher.updateAAD(aad)
        return Encrypted(b64(iv), b64(cipher.doFinal(data, 0, len)))
    }

    private fun b64(b: ByteArray) = Base64.encodeToString(b, Base64.NO_WRAP)
}
