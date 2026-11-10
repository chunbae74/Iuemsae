package kr.ieumsae.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kr.ieumsae.app.data.CommunicationText
import kr.ieumsae.app.data.PasswordRules
import kr.ieumsae.app.data.Session
import kr.ieumsae.app.data.userMessage
import kr.ieumsae.app.ui.AppHeader
import kr.ieumsae.app.ui.C
import kr.ieumsae.app.ui.ErrorText
import kr.ieumsae.app.ui.Field
import kr.ieumsae.app.ui.GhostButton
import kr.ieumsae.app.ui.Ic
import kr.ieumsae.app.ui.PrimaryButton

@Composable
fun SettingsScreen(
    session: Session,
    onCommunication: () -> Unit,
    onChangePassword: () -> Unit,
    onLoggedOut: (String) -> Unit,
    onToast: (String) -> Unit,
    tabs: @Composable () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var withdrawing by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        runCatching { session.profile() }
            .onFailure {
                if (it is kotlinx.coroutines.CancellationException) throw it
                onToast(it.userMessage())
            }
    }

    Column(Modifier.fillMaxSize()) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 22.dp)) {
            Text("설정", fontSize = 26.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(top = 18.dp, bottom = 20.dp))
            GroupLabel("소통 · 소리로 읽기")
            val comm by session.communication.collectAsState()
            val tts by session.ttsConsent.collectAsState()
            var ttsBusy by remember { mutableStateOf(false) }
            Group {
                SettingRow(
                    "소통 정보",
                    CommunicationText.forListener(comm) ?: if (comm != null) "저장됨 · 상대방에게 보여 주지 않음" else "말하기·이해 수준을 알려 주면 상대방이 배려하기 쉬워요",
                    onClick = onCommunication,
                )
                ToggleRow(
                    "감정 음성으로 읽기",
                    "켜면 읽을 문장만 ElevenLabs(미국)로 암호화 전송해 감정을 담은 목소리로 읽어요. 끄면 휴대폰 기본 음성을 써요.",
                    checked = tts,
                    enabled = !ttsBusy,
                ) { agree ->
                    ttsBusy = true
                    scope.launch {
                        try {
                            session.setTtsConsent(agree)
                            onToast(if (agree) "감정 음성 읽기를 켰어요" else "감정 음성 읽기를 껐어요")
                        } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                            onToast(e.userMessage())
                        } finally {
                            ttsBusy = false
                        }
                    }
                }
            }
            GroupLabel("계정")
            Group {
                SettingRow("비밀번호 변경", onClick = onChangePassword)
                SettingRow("로그아웃") {
                    scope.launch {
                        val confirmed = session.logout()
                        onLoggedOut(if (confirmed) "로그아웃했어요" else "이 기기에서 로그아웃했어요. 서버 세션 종료는 확인하지 못했어요.")
                    }
                }
                SettingRow("탈퇴하고 모든 데이터 지우기", danger = true, chevron = false) { withdrawing = true }
            }
            Text(
                "음성과 인식 문장은 서버에 저장하지 않아요. 인식이 끝나거나 취소하면 바로 지워요.",
                color = C.Muted, fontSize = 14.sp, lineHeight = 20.sp, modifier = Modifier.padding(4.dp),
            )
        }
        tabs()
    }

    if (withdrawing) {
        WithdrawSheet(
            onDismiss = { withdrawing = false },
            onConfirm = { pw ->
                session.withdraw(pw)
                withdrawing = false
                onLoggedOut("탈퇴하고 모든 데이터를 지웠어요")
            },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun WithdrawSheet(onDismiss: () -> Unit, onConfirm: suspend (String) -> Unit) {
    val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val scope = rememberCoroutineScope()
    var pw by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = state, containerColor = C.Bg) {
        Column(Modifier.padding(horizontal = 22.dp).padding(bottom = 18.dp).imePadding()) {
            Text("탈퇴할까요?", fontSize = 21.sp, fontWeight = FontWeight.ExtraBold)
            Text(
                "계정, 기기 등록 정보, 동의 내역이 바로 지워지고 되돌릴 수 없어요. 음성과 인식 문장은 원래 저장하지 않아요.",
                color = C.Muted, fontSize = 15.sp, lineHeight = 22.sp, modifier = Modifier.padding(top = 8.dp, bottom = 18.dp),
            )
            Field("비밀번호 확인", pw, { pw = it }, password = true)
            ErrorText(error)
            Row(Modifier.fillMaxWidth().padding(top = 18.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GhostButton("취소", onDismiss, Modifier.weight(1f))
                GhostButton("탈퇴하기", modifier = Modifier.weight(1f), color = Color.White, container = C.Red, onClick = {
                    if (pw.isEmpty() || loading) return@GhostButton
                    loading = true
                    scope.launch {
                        try { onConfirm(pw) } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                error = e.userMessage() } finally { loading = false }
                    }
                })
            }
        }
    }
}

@Composable
fun ChangePasswordScreen(session: Session, onBack: () -> Unit, onDone: (String) -> Unit) {
    var loginId by remember { mutableStateOf<String?>(null) }
    var current by remember { mutableStateOf("") }
    var pw by remember { mutableStateOf("") }
    var pw2 by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) {
        try {
            loginId = session.profile().loginId
        } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
            error = e.userMessage()
        }
    }
    Column(Modifier.fillMaxSize().imePadding().padding(horizontal = 22.dp)) {
        AppHeader(title = "비밀번호 변경", onBack = onBack)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            Heading("지금 비밀번호를 확인하고\n새 비밀번호로 바꿀게요")
            Field("지금 비밀번호", current, { current = it }, password = true)
            Spacer(Modifier.height(18.dp))
            Field("새 비밀번호", pw, { pw = it }, password = true)
            Spacer(Modifier.height(18.dp))
            Field("새 비밀번호 확인", pw2, { pw2 = it }, password = true)
            PasswordChecklist(pw, pw2, loginId.orEmpty())
            if (loginId == null) {
                Text("아이디 포함 여부는 계정 정보를 불러온 뒤 확인해요.", color = C.Muted, fontSize = 14.sp)
            }
            val different = current.isNotEmpty() && pw.isNotEmpty() && current != pw
            PasswordCondition("지금 비밀번호와 다르게 설정하기", different)
            ErrorText(error)
        }
        PrimaryButton("바꾸기", loading = loading, modifier = Modifier.padding(vertical = 16.dp), onClick = {
            if (loading) return@PrimaryButton
            if (current.isEmpty()) { error = "지금 비밀번호를 입력해 주세요"; return@PrimaryButton }
            if (pw != pw2) { error = "새 비밀번호 확인이 맞지 않아요"; return@PrimaryButton }
            if (pw == current) { error = "지금 쓰는 비밀번호와 달라야 해요"; return@PrimaryButton }
            error = null
            loading = true
            scope.launch {
                try {
                    val id = loginId ?: session.profile().loginId.also { loginId = it }
                    if (PasswordRules.evaluate(pw, id).any { !it.met }) {
                        error = "비밀번호 조건을 모두 충족해 주세요"
                        return@launch
                    }
                    session.changePassword(current, pw)
                    onDone("비밀번호를 바꿨어요. 새 비밀번호로 다시 로그인해 주세요.")
                } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                    error = e.userMessage()
                } finally {
                    loading = false
                }
            }
        })
    }
}

@Composable
private fun GroupLabel(text: String) {
    Text(text, color = C.Tab, fontSize = 14.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(start = 4.dp, bottom = 8.dp))
}

@Composable
private fun Group(content: @Composable () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(bottom = 22.dp)
            .border(1.dp, C.Line, RoundedCornerShape(14.dp))
            .background(C.Bg, RoundedCornerShape(14.dp)),
    ) { content() }
}

@Composable
private fun SettingRow(title: String, sub: String? = null, danger: Boolean = false, chevron: Boolean = true, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold, color = if (danger) C.Red else C.Fg)
            if (sub != null) Text(sub, fontSize = 14.sp, color = C.Muted, modifier = Modifier.padding(top = 3.dp))
        }
        if (chevron) Icon(Ic.Chevron, null, tint = Color(0xFF9AA1AD), modifier = Modifier.size(20.dp))
    }
    HorizontalDivider(color = C.Line)
}

@Composable
private fun ToggleRow(title: String, sub: String, checked: Boolean, enabled: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(enabled = enabled) { onChange(!checked) }.padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f).padding(end = 12.dp)) {
            Text(title, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold)
            Text(sub, fontSize = 14.sp, color = C.Muted, lineHeight = 20.sp, modifier = Modifier.padding(top = 3.dp))
        }
        Switch(checked = checked, onCheckedChange = onChange, enabled = enabled, colors = SwitchDefaults.colors(checkedTrackColor = C.Blue))
    }
    HorizontalDivider(color = C.Line)
}
