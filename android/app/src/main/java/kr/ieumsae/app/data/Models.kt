package kr.ieumsae.app.data

import kotlinx.serialization.Serializable

@Serializable data class EmailCodeReq(val email: String, val purpose: String = "signup")
@Serializable data class EmailVerifyReq(val email: String, val code: String, val purpose: String = "signup")
@Serializable data class EmailVerifyRes(val emailToken: String, val expiresIn: Int)
@Serializable
data class Consents(
    val terms: Boolean,
    val privacy: Boolean,
    val sensitiveVoice: Boolean,
    val sensitiveProfile: Boolean = false,
    val ttsOverseas: Boolean = false,
)


@Serializable
data class Communication(
    val speechLevel: Int? = null,
    val comprehensionLevel: Int? = null,
    val showToListener: Boolean = true,
)

@Serializable
data class SignupReq(
    val loginId: String,
    val password: String,
    val emailToken: String,
    val consents: Consents,
    val communication: Communication? = null,
)
@Serializable data class SignupRes(val userId: String)
@Serializable data class LoginReq(val loginId: String, val password: String, val deviceId: String? = null)

@Serializable
data class TokenRes(
    val userId: String? = null,
    val accessToken: String,
    val accessTokenExpiresIn: Int,
    val refreshToken: String,
    val refreshTokenExpiresIn: Int,
    val deviceRegistered: Boolean? = null,
)

@Serializable data class RefreshReq(val refreshToken: String)
@Serializable data class PasswordChangeReq(val currentPassword: String, val newPassword: String)
@Serializable data class FindIdReq(val email: String)
@Serializable data class ResetRequestReq(val loginId: String, val email: String)
@Serializable data class ResetConfirmReq(val loginId: String, val code: String, val newPassword: String)
@Serializable data class ChallengeRes(val challenge: String, val expiresIn: Int)

@Serializable
data class DeviceRegisterReq(
    val challenge: String,
    val publicKey: String,
    val keyAttestationChain: List<String>,
    val integrityToken: String?,
    val sdkInt: Int,
)

@Serializable data class DeviceRegisterRes(val deviceId: String, val securityLevel: String)
@Serializable data class ProfileConsents(val sensitiveProfile: Boolean = false, val ttsOverseas: Boolean = false)

@Serializable
data class ProfileRes(
    val userId: String,
    val loginId: String,
    val email: String,
    val createdAt: Long,
    val communication: Communication? = null,
    val consents: ProfileConsents = ProfileConsents(),
)

@Serializable
data class CommunicationUpdateReq(
    val speechLevel: Int?,
    val comprehensionLevel: Int?,
    val showToListener: Boolean,
    val consent: Boolean,
)

@Serializable data class TtsConsentReq(val agree: Boolean)
@Serializable data class DeleteUserReq(val password: String)

@Serializable data class SttSessionReq(val mode: String)
@Serializable data class SttLimits(val sampleRate: Int, val maxChunkSeconds: Int, val maxChunks: Int)

@Serializable
data class SttSessionRes(
    val sessionId: String,
    val hpkePublicKey: String,
    val serverKeyId: String,
    val signature: String,
    val expiresAt: Long,
    val limits: SttLimits,
)

@Serializable data class SttKeyReq(val enc: String, val ciphertext: String)
@Serializable data class SttChunkReq(val seq: Int, val timestamp: Long, val iv: String, val ciphertext: String)
@Serializable data class SttChunkRes(val received: Int)
@Serializable data class SttFinalizeReq(val lastSeq: Int)
@Serializable data class SttFinalizeRes(val iv: String, val ciphertext: String)
@Serializable data class SttText(val text: String)

@Serializable
data class TtsSessionRes(
    val sessionId: String,
    val hpkePublicKey: String,
    val serverKeyId: String,
    val signature: String,
    val expiresAt: Long,
)

@Serializable data class TtsPayload(val key: String, val text: String, val emotion: String)
@Serializable data class TtsSpeakReq(val enc: String, val ciphertext: String)
@Serializable data class TtsSpeakRes(val iv: String, val ciphertext: String, val mimeType: String)
