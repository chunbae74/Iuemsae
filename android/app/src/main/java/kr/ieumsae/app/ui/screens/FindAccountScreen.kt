package kr.ieumsae.app.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kr.ieumsae.app.data.Session
import kr.ieumsae.app.data.userMessage
import kr.ieumsae.app.ui.AppHeader
import kr.ieumsae.app.ui.ErrorText
import kr.ieumsae.app.ui.Field
import kr.ieumsae.app.ui.InfoCard
import kr.ieumsae.app.ui.PrimaryButton

@Composable
fun FindIdScreen(session: Session, onBack: () -> Unit) {
    var email by rememberSaveable { mutableStateOf("") }
    var sent by rememberSaveable { mutableStateOf(false) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var loading by rememberSaveable { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Column(Modifier.fillMaxSize().imePadding().padding(horizontal = 22.dp)) {
        AppHeader(title = "아이디 찾기", onBack = onBack)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            Heading("가입한 메일로\n아이디를 보내 드릴게요")
            Field("메일 주소", email, { email = it; sent = false }, keyboard = KeyboardType.Email)
            if (sent) {
                Spacer(Modifier.height(16.dp))
                InfoCard("가입한 메일이 맞다면 아이디를 보냈어요. 메일함을 확인해 주세요.")
            }
            ErrorText(error)
        }
        PrimaryButton(if (sent) "로그인으로 돌아가기" else "아이디 받기", loading = loading, modifier = Modifier.padding(vertical = 16.dp), onClick = {
            if (sent) { onBack(); return@PrimaryButton }
            if (!email.contains('@')) { error = "메일 주소를 확인해 주세요"; return@PrimaryButton }
            error = null
            loading = true
            scope.launch {
                try { session.findId(email); sent = true } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                error = e.userMessage() } finally { loading = false }
            }
        })
    }
}

@Composable
fun ResetPasswordScreen(session: Session, onBack: () -> Unit, onDone: () -> Unit) {
    var loginId by rememberSaveable { mutableStateOf("") }
    var email by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    var pw by remember { mutableStateOf("") }
    var pw2 by remember { mutableStateOf("") }
    var requested by rememberSaveable { mutableStateOf(false) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
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
        AppHeader(title = "비밀번호 찾기", onBack = onBack)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            if (!requested) {
                Heading("아이디와 가입한 메일을\n알려 주세요")
                Field("아이디", loginId, { loginId = it.lowercase() })
                Spacer(Modifier.height(18.dp))
                Field("메일 주소", email, { email = it }, keyboard = KeyboardType.Email)
            } else {
                Heading("메일로 받은 코드와\n새 비밀번호를 입력해 주세요")
                InfoCard("아이디와 메일이 맞다면 재설정 코드를 보냈어요. 5분 안에 입력해 주세요.")
                Spacer(Modifier.height(18.dp))
                Field("재설정 코드 6자리", code, { if (it.length <= 6) code = it.filter(Char::isDigit) }, keyboard = KeyboardType.NumberPassword)
                Spacer(Modifier.height(18.dp))
                Field("새 비밀번호", pw, { pw = it }, password = true)
                Spacer(Modifier.height(18.dp))
                Field("새 비밀번호 확인", pw2, { pw2 = it }, password = true)
            }
            ErrorText(error)
        }
        PrimaryButton(if (requested) "비밀번호 바꾸기" else "재설정 코드 받기", loading = loading, modifier = Modifier.padding(vertical = 16.dp), onClick = {
            if (!requested) {
                if (loginId.isBlank() || !email.contains('@')) { error = "아이디와 메일 주소를 확인해 주세요"; return@PrimaryButton }
                run { session.requestReset(loginId, email); requested = true }
            } else {
                if (pw != pw2) { error = "비밀번호 확인이 맞지 않아요"; return@PrimaryButton }
                run { session.confirmReset(loginId, code, pw); pw = ""; pw2 = ""; onDone() }
            }
        })
    }
}

@Composable
internal fun Heading(text: String) {
    Text(text, fontSize = 26.sp, fontWeight = FontWeight.ExtraBold, lineHeight = 36.sp, modifier = Modifier.padding(top = 12.dp, bottom = 24.dp))
}
