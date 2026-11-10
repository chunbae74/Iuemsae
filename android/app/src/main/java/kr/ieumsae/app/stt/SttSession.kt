package kr.ieumsae.app.stt

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kr.ieumsae.app.data.ApiException
import kr.ieumsae.app.data.Session
import kr.ieumsae.app.data.SttChunkReq
import kr.ieumsae.app.data.SttFinalizeReq
import kr.ieumsae.app.data.SttFinalizeRes
import kr.ieumsae.app.data.SttKeyReq
import kr.ieumsae.app.data.SttSessionReq
import kr.ieumsae.app.data.SttSessionRes
import kr.ieumsae.app.data.SttText
import kr.ieumsae.app.security.SttCrypto
import java.util.Arrays
import java.util.concurrent.atomic.AtomicBoolean

class SttSecurityException : Exception("서버 서명을 확인하지 못했습니다")


class SttSession(
    private val context: Context,
    private val session: Session,
) {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val _level = MutableStateFlow(0f)
    val level: StateFlow<Float> = _level.asStateFlow()


    private val _limitReached = MutableStateFlow(false)
    val limitReached: StateFlow<Boolean> = _limitReached.asStateFlow()

    private val stopping = AtomicBoolean(false)
    private val chunks = audioQueue()
    private var maxChunks = 30
    private var totalBytes = 0L

    private lateinit var setup: Deferred<Pair<SttSessionRes, SttCrypto.SessionKey>>
    private lateinit var capture: Job
    private lateinit var upload: Deferred<Int>
    @Volatile private var serverSessionId: String? = null
    @Volatile private var sessionKey: SttCrypto.SessionKey? = null

    private val json get() = session.api.json


    private val _failure = MutableStateFlow<Throwable?>(null)
    val failure: StateFlow<Throwable?> = _failure.asStateFlow()

    fun start() {
        setup = scope.async(Dispatchers.IO) { openServerSession() }
        capture = scope.launch(Dispatchers.IO) {
            try {
                captureLoop()
            } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                _failure.value = e
            }
        }
        upload = scope.async(Dispatchers.IO) { uploadLoop() }
        upload.invokeOnCompletion { e ->
            if (e != null && e !is kotlinx.coroutines.CancellationException) _failure.value = e
        }
    }

    private suspend fun openServerSession(): Pair<SttSessionRes, SttCrypto.SessionKey> {
        val res: SttSessionRes = json.decodeFromString(
            session.authed("POST", "/stt/session", json.encodeToString(SttSessionReq("translate")), signed = true)
        )
        val ok = SttCrypto.verifySession(
            res.sessionId, res.hpkePublicKey, res.serverKeyId, res.expiresAt,
            session.userId.orEmpty(), session.deviceId.orEmpty(), res.signature,
        )
        if (!ok) throw SttSecurityException()
        serverSessionId = res.sessionId
        maxChunks = res.limits.maxChunks
        val key = SttCrypto.newSessionKey()
        return key.transferAfter {
            val sealed = SttCrypto.sealSessionKey(res.sessionId, res.hpkePublicKey, key)
            session.authed(
                "POST", "/stt/session/${res.sessionId}/key",
                json.encodeToString(SttKeyReq(sealed.enc, sealed.ciphertext)), signed = true,
            )
            sessionKey = key
            res to key
        }
    }

    private fun captureLoop() {
        val audio = AudioCapture(context)
        val frame = ByteArray(640)
        var chunk = ByteArray(AudioCapture.BYTES_PER_SECOND)
        var filled = 0
        var sent = 0
        try {
            audio.start()
            while (scope.isActive && !stopping.get()) {
                val n = audio.read(frame)
                if (n < 0) break
                if (n == 0) continue
                _level.value = level(frame, n)
                var off = 0
                while (off < n) {
                    val take = minOf(n - off, chunk.size - filled)
                    System.arraycopy(frame, off, chunk, filled, take)
                    filled += take
                    off += take
                    if (filled == chunk.size) {
                        val completed = chunk
                        chunk = ByteArray(AudioCapture.BYTES_PER_SECOND)
                        filled = 0
                        if (!chunks.enqueueAudio(completed)) {
                            stopping.set(true)
                            break
                        }
                        totalBytes += completed.size
                        sent++
                        if (sent >= maxChunks) {
                            _limitReached.value = true
                            stopping.set(true)
                            break
                        }
                    }
                }
            }
        } finally {
            try {
                audio.stop()
            } finally {
                try {
                    if (filled > 0 && sent < maxChunks && chunks.enqueueAudio(chunk.copyOf(filled))) {
                        totalBytes += filled
                    }
                } finally {
                    Arrays.fill(chunk, 0)
                    Arrays.fill(frame, 0)
                    chunks.close()
                    _level.value = 0f
                }
            }
        }
    }


    private suspend fun uploadLoop(): Int {
        val (res, key) = setup.await()
        var seq = 0
        for (pcm in chunks) {
            try {
                val ts = System.currentTimeMillis()
                val enc = SttCrypto.encryptChunk(key, res.sessionId, seq, ts, pcm, pcm.size)
                session.authed(
                    "POST", "/stt/session/${res.sessionId}/chunk",
                    json.encodeToString(SttChunkReq(seq, ts, enc.iv, enc.ciphertext)), signed = true,
                )
                seq++
            } finally {
                Arrays.fill(pcm, 0)
            }
        }
        return seq
    }


    suspend fun finish(): String {
        try {
            return withContext(Dispatchers.IO) {
                stopping.set(true)
                capture.join()
                val sentChunks = upload.await()
                val (res, key) = setup.await()
                if (sentChunks == 0 || totalBytes < AudioCapture.BYTES_PER_SECOND / 4) {
                    return@withContext ""
                }
                val finalized = session.authed(
                    "POST", "/stt/session/${res.sessionId}/finalize",
                    json.encodeToString(SttFinalizeReq(sentChunks - 1)), signed = true,
                )
                // A successful finalize response means the server already removed the session.
                serverSessionId = null
                val out: SttFinalizeRes = json.decodeFromString(finalized)
                val plain = SttCrypto.decryptResult(key, res.sessionId, out.iv, out.ciphertext)
                try {
                    json.decodeFromString<SttText>(String(plain)).text
                } finally {
                    Arrays.fill(plain, 0)
                }
            }
        } finally {
            // This must also run when cancellation prevents entry into the IO block.
            withContext(NonCancellable + Dispatchers.IO) { cleanup() }
        }
    }


    fun cancel() {
        stopping.set(true)
        scope.launch(Dispatchers.IO + NonCancellable) {
            cleanup()
        }
    }

    private suspend fun cleanup() {
        stopping.set(true)
        chunks.cancel()
        try {
            if (this::capture.isInitialized) capture.cancelAndJoin()
            if (this::upload.isInitialized) upload.cancelAndJoin()
            if (this::setup.isInitialized) setup.cancelAndJoin()
        } finally {
            sessionKey?.wipe()
            sessionKey = null
            serverSessionId?.let { deleteQuietly(it) }
            serverSessionId = null
        }
    }

    private suspend fun deleteQuietly(sessionId: String) {
        try {
            session.authed("DELETE", "/stt/session/$sessionId", signed = true)
        } catch (_: ApiException) {
            // The server also expires abandoned sessions; local wiping is independent.
        } catch (_: java.security.GeneralSecurityException) {
            // A removed device key can prevent signing the best-effort deletion.
        } catch (e: IllegalStateException) {
            if (e is kotlinx.coroutines.CancellationException) throw e
        }
    }
}

fun Throwable.sttMessage(): String = when (this) {
    is SttSecurityException -> "서버를 확인하지 못해 음성을 보내지 않았어요."
    is ApiException -> when (code) {
        "device_not_registered" -> "기기 등록이 필요해요. 앱을 다시 열어 주세요."
        "stt_unavailable" -> "음성인식 서버가 준비 중이에요. 잠시 후 다시 해 주세요."
        "network" -> "서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요."
        else -> "알아듣지 못했어요. 다시 말해 주세요."
    }
    is IllegalStateException -> message ?: "마이크를 쓸 수 없어요."
    else -> "알아듣지 못했어요. 다시 말해 주세요."
}
