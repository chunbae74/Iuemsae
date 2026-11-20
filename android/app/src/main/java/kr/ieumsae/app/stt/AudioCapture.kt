package kr.ieumsae.app.stt

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.content.ContextCompat
import kotlin.math.sqrt


class AudioCapture(private val context: Context) {
    companion object {
        const val SAMPLE_RATE = 16000
        const val BYTES_PER_SECOND = SAMPLE_RATE * 2
        private const val FRAME_BYTES = 640
        private const val TAG = "AudioCapture"

        fun hasPermission(context: Context) =
            ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    }

    private var record: AudioRecord? = null

    @SuppressLint("MissingPermission")
    fun start() {
        check(hasPermission(context)) { "마이크 권한이 없습니다" }
        val min = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val r = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            maxOf(min, BYTES_PER_SECOND / 2),
        )
        var acquired = false
        try {
            check(r.state == AudioRecord.STATE_INITIALIZED) { "마이크를 열지 못했습니다" }
            r.startRecording()
            record = r
            acquired = true
        } finally {
            // Failed starts still own the local recorder; successful ones transfer it to stop().
            if (!acquired) r.release()
        }
    }


    fun read(buf: ByteArray): Int {
        val r = record ?: return -1
        return r.read(buf, 0, minOf(FRAME_BYTES, buf.size))
    }

    fun stop() {
        val current = record ?: return
        record = null
        try {
            current.stop()
        } catch (e: IllegalStateException) {
            // An unstarted or already stopped recorder still needs release().
            Log.w(TAG, "RECORD_STOP_REJECTED reason=${e.javaClass.simpleName}")
        } finally {
            current.release()
        }
    }
}


fun level(buf: ByteArray, len: Int): Float {
    var sum = 0.0
    var n = 0
    var i = 0
    while (i + 1 < len) {
        val s = (buf[i].toInt() and 0xFF) or (buf[i + 1].toInt() shl 8)
        sum += (s.toShort().toDouble()).let { it * it }
        n++
        i += 2
    }
    if (n == 0) return 0f
    return (sqrt(sum / n) / 6000.0).coerceIn(0.0, 1.0).toFloat()
}
