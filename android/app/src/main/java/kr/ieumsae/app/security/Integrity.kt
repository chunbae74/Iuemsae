package kr.ieumsae.app.security

import android.content.Context
import android.util.Base64
import com.google.android.play.core.integrity.IntegrityManagerFactory
import com.google.android.play.core.integrity.IntegrityTokenRequest
import kotlinx.coroutines.suspendCancellableCoroutine
import kr.ieumsae.app.BuildConfig
import kotlin.coroutines.resume


object Integrity {
    suspend fun token(context: Context, challenge: ByteArray): String? {
        require(BuildConfig.CLOUD_PROJECT_NUMBER > 0L)
        val nonce = Base64.encodeToString(challenge, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        return suspendCancellableCoroutine { cont ->
            IntegrityManagerFactory.create(context.applicationContext)
                .requestIntegrityToken(
                    IntegrityTokenRequest.builder()
                        .setNonce(nonce)
                        .setCloudProjectNumber(BuildConfig.CLOUD_PROJECT_NUMBER)
                        .build()
                )
                .addOnSuccessListener { cont.resume(it.token()) }
                .addOnFailureListener { cont.resume(null) }
        }
    }
}
