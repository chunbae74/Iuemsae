package kr.ieumsae.app.security

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import android.util.Base64
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.Signature
import java.security.spec.ECGenParameterSpec


object DeviceKey {
    private const val ALIAS = "ieumsae_device_sign_v1"
    private const val SIG_VERSION = "IEUMSAE-SIG-V1"

    private fun keyStore(): KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    class Attested(val publicKeySpki: String, val chain: List<String>, val strongBox: Boolean)


    fun generate(challenge: ByteArray): Attested {
        delete()
        val strongBox = Build.VERSION.SDK_INT >= 28 && runCatching { generateInternal(challenge, true) }.isSuccess
        if (!strongBox) generateInternal(challenge, false)
        val ks = keyStore()
        val chain = ks.getCertificateChain(ALIAS) ?: error("키 증명 인증서가 없습니다")
        return Attested(
            publicKeySpki = b64(chain[0].publicKey.encoded),
            chain = chain.map { b64(it.encoded) },
            strongBox = strongBox,
        )
    }

    private fun generateInternal(challenge: ByteArray, strongBox: Boolean) {
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setAttestationChallenge(challenge)
            .apply { if (strongBox) setIsStrongBoxBacked(true) }
            .build()
        try {
            KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").apply {
                initialize(spec)
                generateKeyPair()
            }
        } catch (e: StrongBoxUnavailableException) {
            delete()
            throw e
        }
    }

    fun exists(): Boolean = runCatching { keyStore().containsAlias(ALIAS) }.getOrDefault(false)

    fun delete() {
        runCatching { keyStore().deleteEntry(ALIAS) }
    }

    fun isHardwareBacked(): Boolean = runCatching {
        val key = keyStore().getKey(ALIAS, null) as PrivateKey
        val info = KeyFactory.getInstance(key.algorithm, "AndroidKeyStore").getKeySpec(key, KeyInfo::class.java)
        info.securityLevel != KeyProperties.SECURITY_LEVEL_SOFTWARE
    }.getOrDefault(false)


    fun signHeaders(deviceId: String, method: String, path: String, body: ByteArray): Map<String, String> {
        val ts = System.currentTimeMillis().toString()
        val nonce = ByteArray(16).also { SecureRandom().nextBytes(it) }
            .let { Base64.encodeToString(it, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING) }
        val bodyHash = b64(MessageDigest.getInstance("SHA-256").digest(body))
        val message = listOf(SIG_VERSION, method.uppercase(), path, ts, nonce, bodyHash).joinToString("\n")
        val key = keyStore().getKey(ALIAS, null) as? PrivateKey ?: error("기기 키가 없습니다")
        val sig = Signature.getInstance("SHA256withECDSA").run {
            initSign(key)
            update(message.toByteArray())
            sign()
        }
        return mapOf(
            "X-Device-Id" to deviceId,
            "X-Timestamp" to ts,
            "X-Nonce" to nonce,
            "X-Signature" to b64(sig),
        )
    }

    private fun b64(b: ByteArray) = Base64.encodeToString(b, Base64.NO_WRAP)
}
