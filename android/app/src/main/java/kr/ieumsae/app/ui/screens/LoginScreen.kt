package kr.ieumsae.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kr.ieumsae.app.data.Session
import kr.ieumsae.app.data.userMessage
import kr.ieumsae.app.ui.C
import kr.ieumsae.app.ui.ErrorText
import kr.ieumsae.app.ui.Field
import kr.ieumsae.app.ui.LinkButton
import kr.ieumsae.app.ui.Logo
import kr.ieumsae.app.ui.PrimaryButton

@Composable
fun LoginScreen(
    session: Session,
    onLoggedIn: () -> Unit,
    onSignup: () -> Unit,
    onFindId: () -> Unit,
    onResetPassword: () -> Unit,
) {
    var id by rememberSaveable { mutableStateOf("") }

    var pw by remember { mutableStateOf("") }
    var keep by rememberSaveable { mutableStateOf(true) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var loading by rememberSaveable { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun submit() {
        error = when {
            id.isBlank() -> "아이디를 입력해 주세요"
            pw.isEmpty() -> "비밀번호를 입력해 주세요"
            else -> null
        }
        if (error != null) return
        loading = true
        scope.launch {
            try {
                session.login(id, pw, keep)
                pw = ""
                onLoggedIn()
            } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                error = e.userMessage()
            } finally {
                loading = false
            }
        }
    }

    Column(Modifier.fillMaxSize().imePadding().padding(horizontal = 22.dp)) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            Spacer(Modifier.height(48.dp))
            Logo(60.dp)
            Text("이음새", fontSize = 30.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
            Text("말하면, 처음 보는 사람도 알아듣게", color = C.Muted, fontSize = 16.sp)
            Spacer(Modifier.height(30.dp))
            Field("아이디", id, { id = it })
            Spacer(Modifier.height(18.dp))
            Field("비밀번호", pw, { pw = it }, password = true)
            Row(
                Modifier.fillMaxWidth().padding(top = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Checkbox(checked = keep, onCheckedChange = { keep = it }, colors = CheckboxDefaults.colors(checkedColor = C.Blue))
                Text("로그인 상태 유지", fontSize = 17.sp, fontWeight = FontWeight.Bold)
            }
            ErrorText(error)
        }
        PrimaryButton("로그인", ::submit, loading = loading)
        Row(
            Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 16.dp),
            horizontalArrangement = Arrangement.Center,
        ) {
            LinkButton("회원가입", onSignup)
            LinkButton("아이디 찾기", onFindId)
            LinkButton("비밀번호 찾기", onResetPassword)
        }
    }
}
