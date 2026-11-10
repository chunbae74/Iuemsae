package kr.ieumsae.app.ui.screens

import android.Manifest
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kr.ieumsae.app.data.CommunicationText
import kr.ieumsae.app.data.Session
import kr.ieumsae.app.data.userMessage
import kr.ieumsae.app.stt.AudioCapture
import kr.ieumsae.app.stt.SttSession
import kr.ieumsae.app.stt.sttMessage
import kr.ieumsae.app.tts.Emotion
import kr.ieumsae.app.tts.EmotionSpeaker
import kr.ieumsae.app.tts.TtsSecurityException
import kr.ieumsae.app.ui.AppHeader
import kr.ieumsae.app.ui.C
import kr.ieumsae.app.ui.Ic
import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.sin

private sealed interface Phase {
    data object Idle : Phase
    data class Recording(val stt: SttSession) : Phase
    data object Processing : Phase
    data class Result(val text: String) : Phase
}


@Composable
fun ConversationScreen(session: Session, onToast: (String) -> Unit, tabs: @Composable () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var phase by remember { mutableStateOf<Phase>(Phase.Idle) }
    var activeStt by remember { mutableStateOf<SttSession?>(null) }
    var emotion by rememberSaveable { mutableStateOf(Emotion.Neutral) }
    var deviceState by remember { mutableStateOf(if (session.isDeviceRegistered) "ok" else "pending") }

    DisposableEffect(Unit) {
        onDispose { activeStt?.cancel() }
    }

    LaunchedEffect(deviceState) {
        if (deviceState == "pending") {
            deviceState = try {
                session.ensureDevice()
                "ok"
            } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                onToast(e.userMessage())
                "failed"
            }
        }
    }

    fun startRecording() {
        if (deviceState != "ok") {
            if (deviceState == "failed") deviceState = "pending"
            onToast("이 기기를 등록하는 중이에요. 잠시 후 다시 눌러 주세요.")
            return
        }
        val stt = SttSession(context, session)
        activeStt = stt
        stt.start()
        phase = Phase.Recording(stt)
    }

    val micLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) startRecording() else onToast("마이크를 허용해야 말하기를 쓸 수 있어요")
    }

    fun talk() {
        if (AudioCapture.hasPermission(context)) startRecording() else micLauncher.launch(Manifest.permission.RECORD_AUDIO)
    }

    when (val p = phase) {
        Phase.Idle -> HomeContent(onTalk = ::talk, registering = deviceState == "pending", tabs = tabs)
        is Phase.Recording -> RecordContent(
            stt = p.stt,
            onFinish = {
                phase = Phase.Processing
                scope.launch {
                    phase = try {
                        Phase.Result(p.stt.finish())
                    } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                        onToast(e.sttMessage())
                        Phase.Idle
                    } finally {
                        if (activeStt === p.stt) activeStt = null
                    }
                }
            },
            onCancel = {
                p.stt.cancel()
                activeStt = null
                phase = Phase.Idle
                onToast("녹음을 취소하고 음성을 지웠어요")
            },
            onFailure = { e ->
                p.stt.cancel()
                activeStt = null
                phase = Phase.Idle
                onToast(e.sttMessage())
            },
        )
        Phase.Processing -> ProcessingContent()
        is Phase.Result -> ResultContent(
            p.text, session, emotion, onEmotionChange = { emotion = it },
            onBack = { phase = Phase.Idle }, onAgain = ::talk, onToast = onToast,
        )
    }
}

@Composable
private fun HomeContent(onTalk: () -> Unit, registering: Boolean, tabs: @Composable () -> Unit) {
    Column(Modifier.fillMaxSize()) {
        Column(Modifier.weight(1f).padding(horizontal = 22.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            AppHeader()
            Spacer(Modifier.weight(1f))
            Text(
                buildAnnotatedString {
                    append("버튼을 누르고\n")
                    withStyle(SpanStyle(color = C.Blue)) { append("하고 싶은 말") }
                    append("을 들려주세요")
                },
                fontSize = 28.sp, fontWeight = FontWeight.ExtraBold, lineHeight = 39.sp, textAlign = TextAlign.Center,
            )
            Spacer(Modifier.weight(1f))
            Box(
                Modifier
                    .size(168.dp)
                    .background(C.BlueSoft, CircleShape)
                    .clickable(onClick = onTalk)
                    .semantics { contentDescription = "말하기" },
                contentAlignment = Alignment.Center,
            ) {
                Box(Modifier.size(140.dp).background(C.Blue, CircleShape), contentAlignment = Alignment.Center) {
                    Icon(Ic.Mic, null, tint = Color.White, modifier = Modifier.size(50.dp))
                }
            }
            Text("말하기", fontSize = 20.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(top = 12.dp))
            Text(
                if (registering) "기기를 안전하게 등록하는 중…" else " ",
                color = C.Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp, bottom = 18.dp),
            )
        }
        tabs()
    }
}

@Composable
private fun RecordContent(stt: SttSession, onFinish: () -> Unit, onCancel: () -> Unit, onFailure: (Throwable) -> Unit) {
    val level by stt.level.collectAsState()
    val limit by stt.limitReached.collectAsState()
    val failure by stt.failure.collectAsState()
    var seconds by remember { mutableIntStateOf(0) }

    BackHandler(onBack = onCancel)
    LaunchedEffect(Unit) { while (true) { delay(1000); seconds++ } }
    LaunchedEffect(limit) { if (limit) onFinish() }
    LaunchedEffect(failure) { failure?.let(onFailure) }

    Column(Modifier.fillMaxSize().padding(horizontal = 22.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        AppHeader(title = null, onBack = onCancel)
        Text("듣고 있어요", fontSize = 30.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(top = 26.dp, bottom = 6.dp))
        Text("천천히 말해도 괜찮아요", color = C.Muted, fontSize = 17.sp)
        Wave(level, Modifier.fillMaxWidth().height(130.dp).padding(top = 30.dp))
        Text(
            "%d:%02d / 0:30".format(seconds / 60, seconds % 60),
            color = C.Blue, fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 16.dp),
        )
        Spacer(Modifier.weight(1f))
        Box(
            Modifier
                .size(136.dp)
                .border(2.5.dp, C.Blue, CircleShape)
                .clickable(onClick = onFinish)
                .semantics { contentDescription = "다 말했어요" },
            contentAlignment = Alignment.Center,
        ) { Box(Modifier.size(42.dp).background(C.Blue, RoundedCornerShape(9.dp))) }
        Text("다 말했어요", fontSize = 20.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(top = 12.dp))
        TextButton(onClick = onCancel, modifier = Modifier.padding(top = 6.dp, bottom = 22.dp)) {
            Text("취소하고 음성 지우기", color = Color(0xFF4B5160), fontSize = 17.sp, textDecoration = TextDecoration.Underline)
        }
    }
}

@Composable
private fun Wave(level: Float, modifier: Modifier) {
    val t by rememberInfiniteTransition(label = "wave").animateFloat(
        0f, 1000f, infiniteRepeatable(tween(1_000_000, easing = LinearEasing)), label = "t",
    )
    val amp by animateFloatAsState(0.25f + level * 0.75f, tween(120), label = "amp")
    Canvas(modifier) {
        val n = 33
        val gap = size.width / n
        val bw = minOf(7.dp.toPx(), gap * 0.55f)
        for (i in 0 until n) {
            val x = gap * i + gap / 2
            val d = (i - (n - 1) / 2f) / ((n - 1) / 2f)
            val env = exp(-d * d * 2.2f)
            val wob = 0.55f + 0.45f * sin(t * 5.2f + i * 0.9f) * sin(t * 2.3f + i * 0.37f)
            val edge = abs(d) > 0.86f
            val bh = if (edge) bw else maxOf(bw, (size.height - 8) * env * amp * (0.35f + 0.65f * abs(wob)))
            drawRoundRect(
                color = if (i % 3 == 1 && !edge) C.Blue else C.BlueMid,
                topLeft = Offset(x - bw / 2, (size.height - bh) / 2),
                size = Size(bw, bh),
                cornerRadius = CornerRadius(bw / 2),
            )
        }
    }
}

@Composable
private fun ProcessingContent() {
    Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        CircularProgressIndicator(color = C.Blue, strokeWidth = 5.dp, modifier = Modifier.size(64.dp))
        Text("알아듣는 중…", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(top = 24.dp))
    }
}

@Composable
private fun ResultContent(
    text: String,
    session: Session,
    emotion: Emotion,
    onEmotionChange: (Emotion) -> Unit,
    onBack: () -> Unit,
    onAgain: () -> Unit,
    onToast: (String) -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var flipped by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(false) }
    val angle by animateFloatAsState(if (flipped) 180f else 0f, tween(450), label = "flip")
    val speaker = remember { EmotionSpeaker(context, session) }
    val speaking by speaker.speaking.collectAsState()
    val communication by session.communication.collectAsState()
    val caption = CommunicationText.forListener(communication)
    val empty = text.isBlank()

    BackHandler(onBack = onBack)
    DisposableEffect(Unit) { onDispose { speaker.shutdown() } }

    fun speak() {
        if (loading) return
        loading = true
        scope.launch {
            try {
                val engine = speaker.speak(text, emotion)
                if (engine == EmotionSpeaker.Engine.Device && session.ttsConsent.value) {
                    onToast("감정 음성을 쓸 수 없어 기기 음성으로 읽어요")
                }
            } catch (e: TtsSecurityException) {
                onToast("서버를 확인하지 못해 문장을 보내지 않았어요")
            } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                onToast("소리로 읽지 못했어요. 한국어 읽기 음성을 확인해 주세요")
            } finally {
                loading = false
            }
        }
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 22.dp)) {
        AppHeader(title = null, onBack = onBack)
        Column(
            Modifier.weight(1f).fillMaxWidth().padding(top = 12.dp).rotate(angle)
                .background(C.BlueSoft, RoundedCornerShape(18.dp))
                .verticalScroll(rememberScrollState()).padding(22.dp),
        ) {
            if (caption != null && !empty) {
                ComprehensionNotice(caption)
                Spacer(Modifier.height(24.dp))
            }
            Text(
                if (empty) "말소리를 듣지 못했어요.\n조금 더 크게 다시 말해 주세요." else text,
                fontSize = if (empty) 26.sp else 40.sp,
                lineHeight = if (empty) 36.sp else 50.sp,
                fontWeight = FontWeight.ExtraBold,
                color = if (empty) C.Muted else C.Fg,
            )
        }
        if (!empty) {
            Text("읽을 때 느낌", color = C.Muted, fontSize = 14.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 14.dp, bottom = 8.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(Emotion.Neutral, Emotion.Happy, Emotion.Sad, Emotion.Angry).forEach { e ->
                    val selected = e == emotion
                    Text(
                        e.label,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        textAlign = TextAlign.Center,
                        color = if (selected) Color.White else C.Fg,
                        modifier = Modifier
                            .weight(1f)
                            .background(if (selected) C.Blue else C.Soft, RoundedCornerShape(999.dp))
                            .clickable { onEmotionChange(e) }
                            .padding(vertical = 14.dp)
                            .semantics { contentDescription = "${e.label}${if (selected) ", 선택됨" else ""}" },
                    )
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 18.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val label = when {
                loading -> "준비 중"
                speaking -> "읽는 중"
                else -> "소리로 읽기"
            }
            Action(label, Ic.Speaker, Modifier.weight(1f), enabled = !empty) { if (speaking) speaker.stop() else speak() }
            Action("상대 쪽으로", Ic.Rotate, Modifier.weight(1f), selected = flipped, enabled = !empty) { flipped = !flipped }
            Action("이어 말하기", Ic.Mic, Modifier.weight(1f), onClick = { speaker.stop(); onAgain() })
        }
    }
}

@Composable
private fun Action(
    label: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    modifier: Modifier,
    selected: Boolean = false,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    Column(
        modifier
            .background(if (selected) C.BlueSoft else C.Bg, RoundedCornerShape(14.dp))
            .border(1.dp, if (selected) C.Blue else C.Line, RoundedCornerShape(14.dp))
            .clickable(enabled = enabled, onClick = onClick)
            .padding(top = 16.dp, bottom = 14.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(icon, null, tint = if (enabled) C.Blue else C.Line, modifier = Modifier.size(28.dp))
        Text(label, fontSize = 16.sp, fontWeight = FontWeight.Bold, color = if (enabled) C.Fg else C.Muted)
    }
}
