package kr.ieumsae.app.tts

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaDataSource
import android.media.MediaPlayer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.SerializationException
import kr.ieumsae.app.BuildConfig
import kr.ieumsae.app.data.ApiException
import kr.ieumsae.app.data.Session
import kr.ieumsae.app.data.TtsPayload
import kr.ieumsae.app.data.TtsSessionRes
import kr.ieumsae.app.data.TtsSpeakReq
import kr.ieumsae.app.data.TtsSpeakRes
import kr.ieumsae.app.security.SttCrypto
import java.util.Arrays
import java.util.Locale
import java.io.IOException
import java.security.GeneralSecurityException


enum class Emotion(val id: String, val label: String, val pitch: Float, val rate: Float) {
    Neutral("neutral", "보통", 1.0f, 0.95f),
    Happy("happy", "기쁨", 1.2f, 1.05f),
    Sad("sad", "슬픔", 0.85f, 0.82f),
    Angry("angry", "화남", 0.92f, 1.1f),
    Urgent("urgent", "다급함", 1.1f, 1.25f),
    Gentle("gentle", "부드럽게", 1.05f, 0.85f),
}

class TtsSecurityException : Exception("서버 서명을 확인하지 못했습니다")


class EmotionSpeaker(context: Context, private val session: Session) {
    enum class Engine { Expressive, Device }

    private val _speaking = MutableStateFlow(false)
    val speaking: StateFlow<Boolean> = _speaking.asStateFlow()

    private var playback: AudioPlayback<MediaPlayer>? = null
    private var deviceReady = false
    private val device: TextToSpeech = TextToSpeech(context.applicationContext) { status ->
        deviceReady = status == TextToSpeech.SUCCESS
        if (deviceReady) device.language = Locale.KOREAN
    }

    init {
        device.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(id: String?) { _speaking.value = true }
            override fun onDone(id: String?) { _speaking.value = false }
            @Deprecated("Deprecated in Java") override fun onError(id: String?) { _speaking.value = false }
        })
    }

    suspend fun speak(text: String, emotion: Emotion): Engine {
        stop()
        if (session.ttsConsent.value) {
            try {
                val audio = fetchExpressive(text, emotion)
                play(audio)
                return Engine.Expressive
            } catch (e: CancellationException) {
                throw e
            } catch (_: ApiException) {
            } catch (_: IOException) {
            } catch (_: SerializationException) {
            } catch (_: GeneralSecurityException) {
            } catch (_: IllegalArgumentException) {
            } catch (_: IllegalStateException) {
            }
        }
        speakOnDevice(text, emotion)
        return Engine.Device
    }

    private suspend fun fetchExpressive(text: String, emotion: Emotion): ByteArray {
        var decrypted: ByteArray? = null
        var delivered = false
        try {
            val audio = withContext(Dispatchers.IO) { requestExpressive(text, emotion).also { decrypted = it } }
            delivered = true
            return audio
        } finally {
            if (!delivered) decrypted?.fill(0)
        }
    }

    private suspend fun requestExpressive(text: String, emotion: Emotion): ByteArray {
        session.ensureDevice()
        val json = session.api.json
        val res: TtsSessionRes = json.decodeFromString(session.authed("POST", "/tts/session", "{}", signed = true))
        val ok = SttCrypto.verifySession(
            res.sessionId, res.hpkePublicKey, res.serverKeyId, res.expiresAt,
            session.userId.orEmpty(), session.deviceId.orEmpty(), res.signature,
            version = SttCrypto.TTS_SESSION_SIG_VERSION,
        )
        if (!ok) throw TtsSecurityException()
        val key = SttCrypto.newSessionKey()
        try {
            val payload = json.encodeToString(
                TtsPayload(Base64.encodeToString(key.bytes(), Base64.NO_WRAP), text, emotion.id)
            ).toByteArray()
            try {
                val sealed = SttCrypto.sealTtsRequest(res.sessionId, res.hpkePublicKey, payload)
                val out: TtsSpeakRes = json.decodeFromString(
                    session.authed(
                        "POST", "/tts/session/${res.sessionId}/speak",
                        json.encodeToString(TtsSpeakReq(sealed.enc, sealed.ciphertext)), signed = true,
                    )
                )
                return SttCrypto.decryptTtsAudio(key, res.sessionId, out.iv, out.ciphertext)
            } finally {
                Arrays.fill(payload, 0)
            }
        } finally {
            key.wipe()
        }
    }

    private suspend fun play(audio: ByteArray) {
        var owner: AudioPlayback<MediaPlayer>? = null
        var started = false
        try {
            withContext(Dispatchers.Main) {
                val current = AudioPlayback(MediaPlayer(), audio) { it.release() }
                owner = current
                val mp = current.player
                mp.setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                mp.setDataSource(ByteSource(audio))
                mp.setOnPreparedListener {
                    if (playback === current && !current.closed) {
                        try {
                            it.start()
                            _speaking.value = true
                        } catch (_: IllegalStateException) {
                            release(current)
                        }
                    }
                }
                mp.setOnCompletionListener { release(current) }
                mp.setOnErrorListener { _, _, _ -> release(current); true }
                playback = current
                mp.prepareAsync()
            }
            started = true
        } finally {
            if (!started) withContext(NonCancellable + Dispatchers.Main) {
                owner?.let { release(it) } ?: Arrays.fill(audio, 0)
            }
        }
    }

    private fun release(owner: AudioPlayback<MediaPlayer>) {
        if (playback === owner) {
            playback = null
            _speaking.value = false
        }
        owner.close()
    }

    private fun speakOnDevice(text: String, emotion: Emotion) {
        if (!deviceReady) throw ApiException(0, "tts_not_ready")
        device.setPitch(emotion.pitch)
        device.setSpeechRate(emotion.rate)
        device.speak(text, TextToSpeech.QUEUE_FLUSH, null, "ieumsae-result")
    }

    fun stop() {
        try {
            playback?.let {
                try {
                    it.player.stop()
                } catch (_: IllegalStateException) {
                    // A player that is still preparing can reject stop().
                } finally {
                    release(it)
                }
            }
        } finally {
            try {
                if (deviceReady) device.stop()
            } finally {
                _speaking.value = false
            }
        }
    }

    fun shutdown() {
        try {
            stop()
        } finally {
            device.shutdown()
        }
    }


    private class ByteSource(private val data: ByteArray) : MediaDataSource() {
        override fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int): Int {
            if (position >= data.size) return -1
            val n = minOf(size.toLong(), data.size - position).toInt()
            System.arraycopy(data, position.toInt(), buffer, offset, n)
            return n
        }

        override fun getSize(): Long = data.size.toLong()
        override fun close() { Arrays.fill(data, 0) }
    }
}
