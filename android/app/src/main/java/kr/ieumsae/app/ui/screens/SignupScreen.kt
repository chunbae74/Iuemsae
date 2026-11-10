package kr.ieumsae.app.ui.screens

import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kr.ieumsae.app.data.Communication
import kr.ieumsae.app.data.PasswordRules
import kr.ieumsae.app.data.Session
import kr.ieumsae.app.data.userMessage
import kr.ieumsae.app.ui.AppHeader
import kr.ieumsae.app.ui.C
import kr.ieumsae.app.ui.ErrorText
import kr.ieumsae.app.ui.Field
import kr.ieumsae.app.ui.InfoCard
import kr.ieumsae.app.ui.PrimaryButton


@Composable
fun SignupScreen(session: Session, onBack: () -> Unit, onDone: () -> Unit) {
    var step by rememberSaveable { mutableStateOf(0) }
    var email by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    var codeSent by rememberSaveable { mutableStateOf(false) }
    var emailToken by rememberSaveable { mutableStateOf<String?>(null) }
    var id by rememberSaveable { mutableStateOf("") }

    var pw by remember { mutableStateOf("") }
    var pw2 by remember { mutableStateOf("") }
    var terms by rememberSaveable { mutableStateOf(false) }
    var privacy by rememberSaveable { mutableStateOf(false) }
    var voice by rememberSaveable { mutableStateOf(false) }
    var comprehensionLevel by rememberSaveable { mutableStateOf<Int?>(null) }
    var showToListener by rememberSaveable { mutableStateOf(true) }
    var profileConsent by rememberSaveable { mutableStateOf(false) }
    var ttsConsent by rememberSaveable { mutableStateOf(false) }
    val hasCommunication = comprehensionLevel != null
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var info by rememberSaveable { mutableStateOf<String?>(null) }
    var loading by rememberSaveable { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun run(block: suspend () -> Unit) {
        error = null
        loading = true
        scope.launch {
            try { block() } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                error = e.userMessage() } finally { loading = false }
        }
    }

    Column(Modifier.fillMaxSize().imePadding().padding(horizontal = 22.dp)) {
        AppHeader(title = "회원가입", onBack = { if (step > 0) step-- else onBack() })
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            Text("${step + 1} / 4", color = C.Muted, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 8.dp))
            when (step) {
                0 -> {
                    Title("메일로 본인 확인을 할게요")
                    Field("메일 주소", email, { email = it; codeSent = false }, keyboard = KeyboardType.Email, placeholder = "hong@example.com")
                    if (codeSent) {
                        Spacer(Modifier.height(18.dp))
                        Field("인증 코드 6자리", code, { if (it.length <= 6) code = it.filter(Char::isDigit) }, keyboard = KeyboardType.NumberPassword)
                    }
                    info?.let { Spacer(Modifier.height(14.dp)); InfoCard(it) }
                }
                1 -> {
                    Title("아이디와 비밀번호를 정해 주세요")
                    Field("아이디", id, { id = it.lowercase() }, placeholder = "영문 소문자로 시작, 4~20자")
                    Spacer(Modifier.height(18.dp))
                    Field("비밀번호", pw, { pw = it }, password = true)
                    Spacer(Modifier.height(18.dp))
                    Field("비밀번호 확인", pw2, { pw2 = it }, password = true)
                    Spacer(Modifier.height(14.dp))
                    PasswordChecklist(pw, pw2, id)
                }
                2 -> {
                    Title("상대방이 어떻게 도와주면\n좋을지 알려 주세요 (선택)")
                    CommunicationForm(Communication(comprehensionLevel = comprehensionLevel, showToListener = showToListener), showSpeech = false) {
                        comprehensionLevel = it.comprehensionLevel
                        showToListener = it.showToListener
                    }
                }
                else -> {
                    Title("서비스 이용에 동의해 주세요")
                    ConsentRow("[필수] 이용약관 동의", null, terms) { terms = it }
                    ConsentRow("[필수] 개인정보 수집·이용 동의", "아이디, 메일 주소, 기기 공개키를 계정 관리에만 써요.", privacy) { privacy = it }
                    ConsentRow(
                        "[필수] 민감정보(음성) 처리 동의",
                        "말소리는 문장으로 바꾸는 데에만 쓰고, 인식이 끝나면 서버에서 바로 지워요. 음성과 인식 문장은 저장하지 않아요.",
                        voice,
                    ) { voice = it }
                    if (hasCommunication) SensitiveConsentRow(profileConsent, understandingOnly = true) { profileConsent = it }
                    if (hasCommunication) Spacer(Modifier.height(10.dp))
                    ConsentRow(
                        "[선택] 감정 음성 읽기를 위한 국외 이전 동의",
                        "‘소리로 읽기’에서 감정을 담은 목소리를 쓰면, 읽을 문장만 ElevenLabs(미국)로 암호화 전송돼요. " +
                            "동의하지 않으면 휴대폰 기본 음성으로 읽어요. 설정에서 언제든 바꿀 수 있어요.",
                        ttsConsent,
                    ) { ttsConsent = it }
                }
            }
            ErrorText(error)
        }
        val label = when {
            step == 0 && !codeSent -> "인증 코드 받기"
            step == 0 -> "인증하기"
            step == 1 -> "다음"
            step == 2 -> if (hasCommunication) "다음" else "건너뛰기"
            else -> "가입하기"
        }
        PrimaryButton(label, loading = loading, modifier = Modifier.padding(vertical = 16.dp), onClick = {
            when {
                step == 0 && !codeSent -> {
                    if (!email.contains('@')) { error = "메일 주소를 확인해 주세요"; return@PrimaryButton }
                    run {
                        session.sendSignupCode(email)
                        codeSent = true
                        info = "메일로 인증 코드를 보냈어요. 5분 안에 입력해 주세요. 메일이 오지 않으면 스팸함을 확인해 주세요."
                    }
                }
                step == 0 -> run {
                    emailToken = session.verifySignupCode(email, code)
                    step = 1
                }
                step == 1 -> {
                    error = when {
                        !Regex("^[a-z][a-z0-9_]{3,19}$").matches(id) -> "아이디는 영문 소문자로 시작하는 4~20자(영문·숫자·_)로 만들어 주세요."
                        pw != pw2 -> "비밀번호 확인이 맞지 않아요"
                        PasswordRules.evaluate(pw, id).any { !it.met } -> "비밀번호 조건을 모두 충족해 주세요"
                        else -> null
                    }
                    if (error == null) step = 2
                }
                step == 2 -> step = 3
                else -> {
                    if (!(terms && privacy && voice)) { error = "필수 항목에 모두 동의해 주세요"; return@PrimaryButton }
                    if (hasCommunication && !profileConsent) {
                        error = "소통 정보를 저장하려면 민감정보 수집에 동의해 주세요. 원하지 않으면 이전 단계에서 ‘선택 안 함’을 골라 주세요."
                        return@PrimaryButton
                    }
                    val communication = if (hasCommunication) Communication(comprehensionLevel = comprehensionLevel, showToListener = showToListener) else null
                    run {
                        session.signup(id, pw, emailToken ?: error("메일 인증이 필요합니다"), communication, ttsConsent)
                        session.login(id, pw, keep = true)
                        pw = ""; pw2 = ""
                        onDone()
                    }
                }
            }
        })
    }
}

@Composable
private fun Title(text: String) {
    Text(text, fontSize = 26.sp, fontWeight = FontWeight.ExtraBold, lineHeight = 36.sp, modifier = Modifier.padding(top = 8.dp, bottom = 22.dp))
}

@Composable
private fun ConsentRow(title: String, detail: String?, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(bottom = 10.dp)
            .border(1.5.dp, if (checked) C.Blue else C.Line, RoundedCornerShape(14.dp))
            .clickable { onChange(!checked) }
            .padding(12.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Checkbox(checked = checked, onCheckedChange = onChange, colors = CheckboxDefaults.colors(checkedColor = C.Blue))
        Column(Modifier.padding(top = 12.dp, start = 4.dp)) {
            Text(buildAnnotatedString { withStyle(SpanStyle(fontWeight = FontWeight.ExtraBold)) { append(title) } }, fontSize = 17.sp)
            if (detail != null) Text(detail, color = C.Muted, fontSize = 14.sp, lineHeight = 20.sp, modifier = Modifier.padding(top = 4.dp))
        }
    }
}
