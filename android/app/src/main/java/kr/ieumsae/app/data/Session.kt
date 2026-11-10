package kr.ieumsae.app.data

import android.content.Context
import android.os.Build
import android.util.Base64
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.encodeToString
import kr.ieumsae.app.security.DeviceKey
import kr.ieumsae.app.security.Integrity
import kr.ieumsae.app.security.SecureStore


class Session(private val context: Context, val api: Api) {
    enum class State { Unknown, LoggedOut, LoggedIn }

    private val store = SecureStore(context)
    private val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)
    private val refreshLock = Mutex()
    private val restoreLock = Mutex()

    private val _state = MutableStateFlow(State.Unknown)
    val state: StateFlow<State> = _state.asStateFlow()

    @Volatile private var accessToken: String? = null
    @Volatile private var refreshToken: String? = null
    @Volatile var userId: String? = prefs.getString("user_id", null); private set
    @Volatile var deviceId: String? = prefs.getString("device_id", null); private set
    private var keepLoggedIn = prefs.getBoolean("keep", true)

    val isDeviceRegistered: Boolean get() = deviceId != null && DeviceKey.exists()
    val onboardingDone: Boolean get() = prefs.getBoolean("onboarding_done", false)
    fun setOnboardingDone() = prefs.edit().putBoolean("onboarding_done", true).apply()

    private inline fun <reified T> T.encode(): String = api.json.encodeToString(this)
    private inline fun <reified T> String.decode(): T = api.json.decodeFromString(this)


    suspend fun restore(): Unit = restoreLock.withLock {

        if (_state.value != State.Unknown) return@withLock
        refreshToken = store.get("refresh_token")
        if (refreshToken == null) {
            _state.value = State.LoggedOut
            return@withLock
        }
        try {
            refresh()
            runCatching { profile() }
            _state.value = State.LoggedIn
        } catch (e: ApiException) {
            if (e.code == "network") {

                _state.value = State.LoggedIn
            } else {
                clearTokens()
            }
        }
    }

    suspend fun login(loginId: String, password: String, keep: Boolean) {
        val id = deviceId.takeIf { DeviceKey.exists() }
        val body = LoginReq(loginId.trim().lowercase(), password, id).encode()
        val res: TokenRes = api.request(
            "POST", "/auth/login", body,
            signer = id?.let { did -> { m, p, b -> DeviceKey.signHeaders(did, m, p, b) } },
        ).decode()
        if (res.deviceRegistered != true && id != null) forgetDevice()
        keepLoggedIn = keep
        prefs.edit().putBoolean("keep", keep).putString("user_id", res.userId).apply()
        userId = res.userId
        saveTokens(res)

        runCatching { profile() }
        _state.value = State.LoggedIn
    }


    suspend fun ensureDevice(): String? {
        if (isDeviceRegistered) return null
        val ch: ChallengeRes = authed("POST", "/device/challenge").decode()
        val challenge = Base64.decode(ch.challenge, Base64.NO_WRAP)
        val attested = DeviceKey.generate(challenge)
        val integrity = Integrity.token(context, challenge)
        val res: DeviceRegisterRes = authed(
            "POST", "/device/register",
            DeviceRegisterReq(ch.challenge, attested.publicKeySpki, attested.chain, integrity, Build.VERSION.SDK_INT).encode(),
        ).decode()
        deviceId = res.deviceId
        prefs.edit().putString("device_id", res.deviceId).apply()

        refreshLock.withLock { refreshLocked() }
        return res.securityLevel
    }

    suspend fun logout(): Boolean = revokeAndClear(
        revoke = { refreshToken?.let { api.request("POST", "/auth/logout", RefreshReq(it).encode()) } },
        clearLocal = ::clearTokens,
    )

    suspend fun changePassword(current: String, new: String) {
        authed("PUT", "/auth/password", PasswordChangeReq(current, new).encode())

        clearTokens()
    }

    suspend fun withdraw(password: String) {
        authed("DELETE", "/user", DeleteUserReq(password).encode())
        forgetDevice()
        clearTokens()
        prefs.edit().clear().apply()
        store.clear()
    }


    private val _communication = MutableStateFlow(
        store.get("communication")?.let { runCatching { api.json.decodeFromString<Communication>(it) }.getOrNull() }
    )

    val communication: StateFlow<Communication?> = _communication.asStateFlow()

    private val _ttsConsent = MutableStateFlow(prefs.getBoolean("tts_consent", false))

    val ttsConsent: StateFlow<Boolean> = _ttsConsent.asStateFlow()

    private fun cacheCommunication(c: Communication?) {
        _communication.value = c
        store.put("communication", c?.let { api.json.encodeToString(it) })
    }

    private fun cacheTtsConsent(agree: Boolean) {
        _ttsConsent.value = agree
        prefs.edit().putBoolean("tts_consent", agree).apply()
    }

    suspend fun profile(): ProfileRes {
        val p: ProfileRes = authed("GET", "/user/profile").decode()
        cacheCommunication(p.communication)
        cacheTtsConsent(p.consents.ttsOverseas)
        return p
    }

    suspend fun saveCommunication(c: Communication) {
        authed(
            "PUT", "/user/communication",
            CommunicationUpdateReq(c.speechLevel, c.comprehensionLevel, c.showToListener, consent = true).encode(),
        )
        cacheCommunication(c)
    }

    suspend fun deleteCommunication() {
        authed("DELETE", "/user/communication")
        cacheCommunication(null)
    }

    suspend fun setTtsConsent(agree: Boolean) {
        authed("PUT", "/user/consents/tts", TtsConsentReq(agree).encode())
        cacheTtsConsent(agree)

        refreshLock.withLock { refreshLocked() }
    }


    suspend fun authed(method: String, path: String, body: String? = null, signed: Boolean = false): String {
        suspend fun once(): String {
            val token = accessToken ?: refresh()
            var signer: ((String, String, ByteArray) -> Map<String, String>)? = null
            if (signed) {
                val did = deviceId ?: throw ApiException(403, "device_not_registered")
                signer = { m, p, b -> DeviceKey.signHeaders(did, m, p, b) }
            }
            return api.request(method, path, body, token, signer)
        }
        return try {
            once()
        } catch (e: ApiException) {
            if (e.status != 401 || e.code !in setOf("invalid_token", "unauthorized")) throw e
            accessToken = null
            once()
        }
    }

    private suspend fun refresh(): String = refreshLock.withLock {
        accessToken ?: refreshLocked()
    }

    private suspend fun refreshLocked(): String {
        val rt = refreshToken ?: run { clearTokens(); throw ApiException(401, "logged_out") }
        val res: TokenRes = try {
            api.request("POST", "/auth/refresh", RefreshReq(rt).encode()).decode()
        } catch (e: ApiException) {
            if (e.status == 401) clearTokens()
            throw e
        }
        saveTokens(res)
        return res.accessToken
    }

    private fun saveTokens(res: TokenRes) {
        accessToken = res.accessToken
        refreshToken = res.refreshToken
        store.put("refresh_token", if (keepLoggedIn) res.refreshToken else null)
    }

    private fun clearTokens() {
        accessToken = null
        refreshToken = null
        store.put("refresh_token", null)

        cacheCommunication(null)
        cacheTtsConsent(false)
        _state.value = State.LoggedOut
    }

    private fun forgetDevice() {
        DeviceKey.delete()
        deviceId = null
        prefs.edit().remove("device_id").apply()
    }


    suspend fun sendSignupCode(email: String) {
        api.request("POST", "/auth/email/code", EmailCodeReq(email.trim().lowercase()).encode())
    }

    suspend fun verifySignupCode(email: String, code: String): String =
        api.request("POST", "/auth/email/verify", EmailVerifyReq(email.trim().lowercase(), code.trim()).encode())
            .decode<EmailVerifyRes>().emailToken

    suspend fun signup(
        loginId: String,
        password: String,
        emailToken: String,
        communication: Communication?,
        ttsOverseas: Boolean,
    ) {
        val consents = Consents(
            terms = true,
            privacy = true,
            sensitiveVoice = true,
            sensitiveProfile = communication != null,
            ttsOverseas = ttsOverseas,
        )
        api.request(
            "POST", "/auth/signup",
            SignupReq(loginId.trim().lowercase(), password, emailToken, consents, communication).encode(),
        )
    }

    suspend fun findId(email: String) {
        api.request("POST", "/auth/find-id", FindIdReq(email.trim().lowercase()).encode())
    }

    suspend fun requestReset(loginId: String, email: String) {
        api.request("POST", "/auth/password-reset/request", ResetRequestReq(loginId.trim().lowercase(), email.trim().lowercase()).encode())
    }

    suspend fun confirmReset(loginId: String, code: String, newPassword: String) {
        api.request("POST", "/auth/password-reset/confirm", ResetConfirmReq(loginId.trim().lowercase(), code.trim(), newPassword).encode())
    }
}

internal suspend fun revokeAndClear(revoke: suspend () -> Unit, clearLocal: () -> Unit): Boolean =
    try {
        revoke()
        true
    } catch (_: ApiException) {
        false
    } finally {
        clearLocal()
    }
