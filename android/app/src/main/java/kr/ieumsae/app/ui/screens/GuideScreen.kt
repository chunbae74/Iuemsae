package kr.ieumsae.app.ui.screens

import android.Manifest
import android.content.Context
import android.content.Intent
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kr.ieumsae.app.stt.AudioCapture
import kr.ieumsae.app.ui.AppHeader
import kr.ieumsae.app.ui.C
import kr.ieumsae.app.ui.Ic
import kr.ieumsae.app.ui.PrimaryButton
import java.util.Locale


@Composable
fun GuideScreen(onDone: () -> Unit, onBack: (() -> Unit)? = null) {
    val context = LocalContext.current
    var step by rememberSaveable { mutableStateOf(0) }
    var micNote by rememberSaveable { mutableStateOf("말소리를 인식하려면 마이크 권한이 필요해요") }
    var voiceNote by rememberSaveable { mutableStateOf("없으면 설치 화면으로 안내해요") }

    val micLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        micNote = if (granted) "마이크를 쓸 수 있어요" else "허용하지 않으면 말하기를 쓸 수 없어요. 설정에서 바꿀 수 있어요"
        step = 2
    }


    val labels = listOf("음성 처리에 동의하기", "마이크 허용하기", "읽기 음성 확인하기", "시작하기")

    Column(Modifier.fillMaxSize().padding(horizontal = 22.dp)) {
        AppHeader(onBack = onBack, title = if (onBack == null) "이음새" else null) {
            Text("${minOf(step + 1, 3)} / 3", color = C.Muted, fontSize = 15.sp, fontWeight = FontWeight.Bold)
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            Text(
                buildAnnotatedString {
                    append("시작하기 전에\n")
                    withStyle(SpanStyle(color = C.Blue)) { append("세 가지") }
                    append("만 준비할게요")
                },
                fontSize = 27.sp, fontWeight = FontWeight.ExtraBold, lineHeight = 37.sp,
                modifier = Modifier.padding(top = 18.dp, bottom = 22.dp),
            )
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                StepRow(0, step, "음성 처리 동의", "음성은 인식 후 바로 지우고 저장하지 않아요")
                StepRow(1, step, "마이크 허용", micNote)
                StepRow(2, step, "한국어 읽기 음성 확인", voiceNote)
            }
        }
        PrimaryButton(labels[step], modifier = Modifier.padding(top = 16.dp, bottom = 16.dp), onClick = {
            when (step) {
                0 -> step = 1
                1 -> if (AudioCapture.hasPermission(context)) { micNote = "마이크를 쓸 수 있어요"; step = 2 }
                     else micLauncher.launch(Manifest.permission.RECORD_AUDIO)
                2 -> checkKoreanVoice(context) { ok ->
                    voiceNote = if (ok) "한국어 읽기 음성이 있어요" else "한국어 음성이 없어 설치 화면을 열었어요"
                    if (!ok) runCatching {
                        context.startActivity(Intent(TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    }
                    step = 3
                }
                else -> onDone()
            }
        })
    }
}

private fun checkKoreanVoice(context: Context, done: (Boolean) -> Unit) {
    var tts: TextToSpeech? = null
    tts = TextToSpeech(context.applicationContext) { status ->
        val ok = status == TextToSpeech.SUCCESS &&
            (tts?.isLanguageAvailable(Locale.KOREAN) ?: TextToSpeech.LANG_NOT_SUPPORTED) >= TextToSpeech.LANG_AVAILABLE
        tts?.shutdown()
        android.os.Handler(context.mainLooper).post { done(ok) }
    }
}

@Composable
private fun StepRow(index: Int, current: Int, title: String, note: String) {
    val done = index < current
    val active = index == current
    Row(
        Modifier
            .fillMaxWidth()
            .background(if (active) C.Bg else C.Soft, RoundedCornerShape(14.dp))
            .border(1.5.dp, if (active) C.Blue else Color.Transparent, RoundedCornerShape(14.dp))
            .padding(horizontal = 16.dp, vertical = 15.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Box(
            Modifier.size(28.dp).background(
                when { done -> C.Green; active -> C.Blue; else -> Color(0xFFE6E9EF) }, CircleShape,
            ),
            contentAlignment = Alignment.Center,
        ) {
            if (done) Icon(Ic.Check, null, tint = Color.White, modifier = Modifier.size(16.dp))
            else Text("${index + 1}", color = if (active) Color.White else C.Muted, fontWeight = FontWeight.ExtraBold, fontSize = 14.sp)
        }
        Column(Modifier.padding(start = 12.dp)) {
            Text(title, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(top = 2.dp))
            Text(note, fontSize = 14.sp, color = C.Muted, lineHeight = 20.sp, modifier = Modifier.padding(top = 4.dp))
        }
    }
}
