package kr.ieumsae.app.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kr.ieumsae.app.data.PasswordRules
import kr.ieumsae.app.ui.C

@Composable
fun PasswordChecklist(password: String, confirmation: String, loginId: String) {
    Column(Modifier.padding(top = 12.dp)) {
        Text("문자 종류: 영문 대문자 · 소문자 · 숫자 · 기타 문자(특수문자 등)", fontSize = 14.sp, color = C.Muted)
        val rules = PasswordRules.evaluate(password, loginId) +
            PasswordRules.Rule("비밀번호 확인 일치", password.isNotEmpty() && password == confirmation)
        rules.forEach { rule ->
            PasswordCondition(rule.label, rule.met)
        }
    }
}

@Composable
fun PasswordCondition(label: String, met: Boolean) {
    Text(
        "${if (met) "✓" else "○"}  $label",
        color = if (met) C.Green else C.Red,
        fontSize = 15.sp, lineHeight = 22.sp, fontWeight = FontWeight.Medium,
        modifier = Modifier.padding(top = 6.dp).semantics {
            stateDescription = if (met) "조건 충족" else "조건 미충족"
        },
    )
}
