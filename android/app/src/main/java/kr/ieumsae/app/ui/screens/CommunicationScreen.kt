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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.TextButton
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kr.ieumsae.app.data.Communication
import kr.ieumsae.app.data.CommunicationText
import kr.ieumsae.app.data.Session
import kr.ieumsae.app.data.userMessage
import kr.ieumsae.app.ui.AppHeader
import kr.ieumsae.app.ui.C
import kr.ieumsae.app.ui.ErrorText
import kr.ieumsae.app.ui.GhostButton
import kr.ieumsae.app.ui.InfoCard
import kr.ieumsae.app.ui.PrimaryButton


@Composable
fun CommunicationForm(value: Communication, showSpeech: Boolean = true, onChange: (Communication) -> Unit) {
    Column {
        InfoCard(
            "고르면 인식 결과 화면에 이해하기 안내를 크게 보여 줘서, 상대방이 천천히 또는 쉬운 말로 말해 주도록 도와요. " +
                "고르지 않아도 되고, 언제든 설정에서 바꾸거나 지울 수 있어요."
        )
        Spacer(Modifier.height(20.dp))
        if (showSpeech) {
            LevelGroup("말하기", CommunicationText.speechOptions, value.speechLevel) { onChange(value.copy(speechLevel = it)) }
            Spacer(Modifier.height(20.dp))
        }
        LevelGroup("말 이해하기", CommunicationText.comprehensionOptions, value.comprehensionLevel) {
            onChange(value.copy(comprehensionLevel = it))
        }
        Spacer(Modifier.height(18.dp))
        Row(Modifier.fillMaxWidth().clickable { onChange(value.copy(showToListener = !value.showToListener)) }, verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("이해하기 안내를 결과 화면에 보여 주기", fontSize = 17.sp, fontWeight = FontWeight.ExtraBold)
                Text("끄면 저장만 하고 상대방에게 보여 주지 않아요", fontSize = 14.sp, color = C.Muted)
            }
            Switch(
                checked = value.showToListener,
                onCheckedChange = { onChange(value.copy(showToListener = it)) },
                colors = SwitchDefaults.colors(checkedTrackColor = C.Blue),
            )
        }
        CommunicationText.forListener(value)?.let {
            Spacer(Modifier.height(14.dp))
            Text("상대방에게 이렇게 보여요", fontSize = 14.sp, color = C.Muted, fontWeight = FontWeight.Bold)
            ComprehensionNotice(it)
        }
    }
}

@Composable
private fun LevelGroup(title: String, options: List<Pair<Int, String>>, selected: Int?, onSelect: (Int?) -> Unit) {
    Text(title, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(bottom = 10.dp))
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        (options + (null to "선택 안 함")).forEach { (level, label) ->
            val on = level == selected
            Text(
                label,
                fontSize = 16.sp,
                fontWeight = if (on) FontWeight.ExtraBold else FontWeight.Medium,
                color = if (on) C.Blue else C.Fg,
                modifier = Modifier
                    .fillMaxWidth()
                    .background(if (on) C.BlueSoft else C.Bg, RoundedCornerShape(12.dp))
                    .border(1.5.dp, if (on) C.Blue else C.Line, RoundedCornerShape(12.dp))
                    .clickable { onSelect(level) }
                    .semantics {
                        role = Role.RadioButton
                        this.selected = on
                    }
                    .padding(horizontal = 16.dp, vertical = 14.dp),
            )
        }
    }
}


@Composable
fun CommunicationSettingsScreen(session: Session, onBack: () -> Unit, onToast: (String) -> Unit) {
    val saved by session.communication.collectAsState()
    var value by remember { mutableStateOf(saved ?: Communication()) }
    var showConsentDialog by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }
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

    suspend fun save() {
        session.saveCommunication(value)
        onToast("소통 정보를 저장했어요")
        onBack()
    }

    if (showConsentDialog) {
        AlertDialog(
            onDismissRequest = { showConsentDialog = false },
            title = { Text("소통 정보 저장에 동의해 주세요") },
            text = {
                Text("[선택] 민감정보(이해 수준) 수집 동의\n\n선택한 이해 수준은 결과 화면의 ‘저와 대화할 때’ 안내에 사용하며, 서버에 암호화해 보관해요. 소통 정보에서 ‘지우기’를 누르면 정보를 삭제하고 동의를 철회해요.\n\n동의하지 않으면 소통 정보를 저장하지 않아요.")
            },
            confirmButton = {
                TextButton(onClick = {
                    showConsentDialog = false
                    run { save() }
                }) { Text("동의하고 저장") }
            },
            dismissButton = {
                TextButton(onClick = { showConsentDialog = false }) { Text("취소") }
            },
        )
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 22.dp)) {
        AppHeader(title = "소통 정보", onBack = onBack)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            Heading("상대방이 어떻게 도와주면\n좋을지 알려 주세요")
            CommunicationForm(value, showSpeech = false) { value = it }
            Spacer(Modifier.height(16.dp))
            ErrorText(error)
        }
        Row(Modifier.fillMaxWidth().padding(vertical = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (saved != null) {
                GhostButton("지우기", modifier = Modifier.weight(1f), color = C.Red, onClick = {
                    run {
                        session.deleteCommunication()
                        onToast("소통 정보를 지우고 동의를 철회했어요")
                        onBack()
                    }
                })
            }
            PrimaryButton("저장하기", loading = loading, modifier = Modifier.weight(2f), onClick = {
                if (value.comprehensionLevel == null) {
                    error = "하나 이상 골라 주세요. 저장된 정보를 없애려면 지우기를 눌러 주세요."
                    return@PrimaryButton
                }
                run {

                    if (session.profile().consents.sensitiveProfile) {
                        save()
                    } else {
                        showConsentDialog = true
                    }
                }
            })
        }
    }
}

@Composable
fun SensitiveConsentRow(checked: Boolean, understandingOnly: Boolean = false, onChange: (Boolean) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .border(1.5.dp, if (checked) C.Blue else C.Line, RoundedCornerShape(14.dp))
            .clickable { onChange(!checked) }
            .padding(12.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Checkbox(checked = checked, onCheckedChange = onChange, colors = CheckboxDefaults.colors(checkedColor = C.Blue))
        Column(Modifier.padding(top = 12.dp, start = 4.dp)) {
            Text(if (understandingOnly) "[선택] 민감정보(이해 수준) 수집 동의" else "[선택] 민감정보(말하기·이해 수준) 수집 동의", fontSize = 16.sp, fontWeight = FontWeight.ExtraBold)
            Text(
                "결과 화면 안내에만 쓰고, 서버에 암호화해 보관해요. 동의를 철회하면 바로 지워요.",
                color = C.Muted, fontSize = 14.sp, lineHeight = 20.sp, modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}
