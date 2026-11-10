package kr.ieumsae.app

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import kotlinx.coroutines.delay
import kr.ieumsae.app.data.Session
import kr.ieumsae.app.ui.C
import kr.ieumsae.app.ui.Ic
import kr.ieumsae.app.ui.IeumsaeTheme
import kr.ieumsae.app.ui.screens.ChangePasswordScreen
import kr.ieumsae.app.ui.screens.CommunicationSettingsScreen
import kr.ieumsae.app.ui.screens.ConversationScreen
import kr.ieumsae.app.ui.screens.FindIdScreen
import kr.ieumsae.app.ui.screens.GuideScreen
import kr.ieumsae.app.ui.screens.LoginScreen
import kr.ieumsae.app.ui.screens.ResetPasswordScreen
import kr.ieumsae.app.ui.screens.SettingsScreen
import kr.ieumsae.app.ui.screens.SignupScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        enableEdgeToEdge()
        val session = app.session
        setContent {
            IeumsaeTheme {
                Box(Modifier.fillMaxSize().background(C.Bg).safeDrawingPadding()) {
                    AppRoot(session)
                }
            }
        }
    }
}

@Composable
private fun AppRoot(session: Session) {
    val state by session.state.collectAsState()
    var toast by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { session.restore() }
    LaunchedEffect(toast) { if (toast != null) { delay(2600); toast = null } }

    Box(Modifier.fillMaxSize()) {
        when (state) {
            Session.State.Unknown -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = C.Blue)
            }
            Session.State.LoggedOut -> LoggedOutNav(session) { toast = it }
            Session.State.LoggedIn -> LoggedInNav(session) { toast = it }
        }
        toast?.let {
            Text(
                it,
                color = Color.White,
                fontSize = 16.sp,
                lineHeight = 22.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(start = 18.dp, end = 18.dp, bottom = 96.dp)
                    .fillMaxWidth()
                    .background(Color(0xEB15171C), RoundedCornerShape(14.dp))
                    .padding(horizontal = 16.dp, vertical = 13.dp),
            )
        }
    }
}

@Composable
private fun LoggedOutNav(session: Session, toast: (String) -> Unit) {
    val nav = rememberNavController()
    NavHost(nav, startDestination = "login") {
        composable("login") {
            LoginScreen(
                session,
                onLoggedIn = {},
                onSignup = { nav.navigate("signup") },
                onFindId = { nav.navigate("find-id") },
                onResetPassword = { nav.navigate("reset") },
            )
        }
        composable("signup") { SignupScreen(session, onBack = { nav.popBackStack() }, onDone = {}) }
        composable("find-id") { FindIdScreen(session, onBack = { nav.popBackStack() }) }
        composable("reset") {
            ResetPasswordScreen(session, onBack = { nav.popBackStack() }, onDone = {
                nav.popBackStack()
                toast("비밀번호를 바꿨어요. 새 비밀번호로 로그인해 주세요.")
            })
        }
    }
}

@Composable
private fun LoggedInNav(session: Session, toast: (String) -> Unit) {
    val nav = rememberNavController()
    val start = if (session.onboardingDone) "home" else "guide"
    NavHost(nav, startDestination = start) {
        composable("guide") {
            GuideScreen(onDone = {
                session.setOnboardingDone()
                nav.navigate("home") { popUpTo("guide") { inclusive = true } }
            })
        }
        composable("home") {
            ConversationScreen(session, onToast = toast) { Tabs(nav, "home") }
        }
        composable("settings") {
            SettingsScreen(
                session,
                onCommunication = { nav.navigate("communication") },
                onChangePassword = { nav.navigate("password") },
                onLoggedOut = toast,
                onToast = toast,
            ) { Tabs(nav, "settings") }
        }
        composable("communication") {
            CommunicationSettingsScreen(session, onBack = { nav.popBackStack() }, onToast = toast)
        }
        composable("password") {
            ChangePasswordScreen(session, onBack = { nav.popBackStack() }, onDone = toast)
        }
    }
}

@Composable
private fun Tabs(nav: NavHostController, current: String) {
    HorizontalDivider(color = C.Line)
    Row(Modifier.fillMaxWidth().padding(top = 6.dp, bottom = 6.dp)) {
        Tab("대화", Ic.Chat, current == "home", Modifier.weight(1f)) {
            if (current != "home") nav.navigate("home") { popUpTo("home") { inclusive = true } }
        }
        Tab("설정", Ic.Sliders, current == "settings", Modifier.weight(1f)) {
            if (current != "settings") nav.navigate("settings") { launchSingleTop = true }
        }
    }
}

@Composable
private fun Tab(label: String, icon: androidx.compose.ui.graphics.vector.ImageVector, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val color = if (selected) C.Blue else C.Tab
    TextButton(onClick = onClick, modifier = modifier) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(icon, null, tint = color, modifier = Modifier.size(24.dp))
            Text(label, color = color, fontSize = 14.sp, fontWeight = FontWeight.Bold)
        }
    }
}
