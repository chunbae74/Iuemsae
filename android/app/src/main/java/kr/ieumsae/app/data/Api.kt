package kr.ieumsae.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kr.ieumsae.app.BuildConfig
import okhttp3.CertificatePinner
import okhttp3.CipherSuite
import okhttp3.ConnectionSpec
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.TlsVersion
import java.io.IOException
import java.util.concurrent.TimeUnit

class ApiException(val status: Int, val code: String) :
    Exception("request_failed")


class Api {
    val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }
    private val base = BuildConfig.API_BASE_URL.toHttpUrl()
    private val jsonType = "application/json".toMediaType()

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectionSpecs(
            listOf(
                ConnectionSpec.Builder(ConnectionSpec.RESTRICTED_TLS)
                    .tlsVersions(TlsVersion.TLS_1_3)

                    .cipherSuites(CipherSuite.TLS_AES_256_GCM_SHA384, CipherSuite.TLS_AES_128_GCM_SHA256)
                    .build()
            )
        )
        .certificatePinner(CertificatePinner.Builder().add(base.host, BuildConfig.TLS_PIN).build())
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .callTimeout(40, TimeUnit.SECONDS)
        .followRedirects(false)
        .followSslRedirects(false)
        .retryOnConnectionFailure(false)
        .build()


    private val profileClient = client.newBuilder().retryOnConnectionFailure(true).build()


    suspend fun request(
        method: String,
        path: String,
        body: String? = null,
        accessToken: String? = null,
        signer: ((String, String, ByteArray) -> Map<String, String>)? = null,
    ): String = withContext(Dispatchers.IO) {
        val bytes = body?.toByteArray() ?: ByteArray(0)
        val url = base.newBuilder().encodedPath(path).build()
        val rb = Request.Builder().url(url)
        rb.method(method, if (body != null || method in setOf("POST", "PUT")) bytes.toRequestBody(jsonType) else null)
        accessToken?.let { rb.header("Authorization", "Bearer $it") }
        signer?.invoke(method, path, bytes)?.forEach { (k, v) -> rb.header(k, v) }
        val requestClient = if (
            (method == "GET" && path == "/user/profile") ||
            (method == "PUT" && path == "/user/communication")
        ) profileClient else client
        try {
            requestClient.newCall(rb.build()).execute().use { resp ->
                val text = resp.body?.string().orEmpty()
                if (!resp.isSuccessful) throw parseError(resp.code, text)
                text
            }
        } catch (e: IOException) {
            throw ApiException(0, "network")
        }
    }

    private fun parseError(status: Int, text: String): ApiException = runCatching {
        when (val err = json.parseToJsonElement(text).jsonObject["error"]) {
            is JsonPrimitive -> ApiException(status, err.content)
            is JsonObject -> ApiException(
                status,
                err["code"]?.jsonPrimitive?.contentOrNull ?: "error",
            )
            else -> ApiException(status, "error")
        }
    }.getOrElse { ApiException(status, "error") }
}


fun Throwable.userMessage(): String {
    val e = this as? ApiException ?: return "문제가 생겼어요. 잠시 후 다시 해 주세요."
    return when (e.code) {
        "weak_password" -> "비밀번호 조건을 모두 충족해 주세요."
        "same_password" -> "지금 쓰는 비밀번호와 달라야 해요."
        "mail_unavailable" -> "인증 메일을 보내지 못했어요. 잠시 후 다시 해 주세요."
        "stt_busy" -> "음성인식 요청이 많아요. 잠시 후 다시 해 주세요."
        "network" -> "서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요."
        "invalid_credentials" -> "아이디 또는 비밀번호가 맞지 않아요."
        "account_locked" -> "로그인에 여러 번 실패해 잠시 잠겼어요. 15분 뒤 다시 하거나 비밀번호를 재설정해 주세요."
        "invalid_code" -> "인증 코드가 맞지 않거나 시간이 지났어요."
        "invalid_email_token" -> "메일 인증 시간이 지났어요. 처음부터 다시 해 주세요."
        "login_id_taken" -> "이미 쓰고 있는 아이디예요."
        "email_taken" -> "이미 가입한 메일이에요."
        "invalid_login_id" -> "아이디는 영문 소문자로 시작하는 4~20자(영문·숫자·_)로 만들어 주세요."
        "consent_required" -> "필수 동의 항목에 모두 동의해 주세요."
        "invalid_password" -> "비밀번호가 맞지 않아요."
        "too_many_requests" -> "요청이 너무 많아요. 잠시 후 다시 해 주세요."
        "stt_unavailable" -> "음성인식 서버가 준비 중이에요. 잠시 후 다시 해 주세요."
        "attestation_failed", "integrity_failed" -> "이 기기를 안전하게 등록하지 못했어요."
        "invalid_request" -> "입력한 내용을 다시 확인해 주세요."
        else -> if (e.status >= 500) "서버에 문제가 생겼어요. 잠시 후 다시 해 주세요." else "요청을 처리하지 못했어요."
    }
}
