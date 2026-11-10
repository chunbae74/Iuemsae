package kr.ieumsae.app.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp


object C {
    val Bg = Color(0xFFFFFFFF)
    val Fg = Color(0xFF15171C)
    val Muted = Color(0xFF6B7280)
    val Soft = Color(0xFFF4F6F9)
    val Line = Color(0xFFE2E6ED)
    val Blue = Color(0xFF2563EB)
    val BlueSoft = Color(0xFFEFF4FE)
    val BlueMid = Color(0xFF93B4F6)
    val BlueDeep = Color(0xFF1745B5)
    val Green = Color(0xFF1E874B)
    val Red = Color(0xFFD12C3A)
    val Chat = Color(0xFFF3F4F7)
    val Tab = Color(0xFF8A919E)
}

private val Bold = FontWeight.ExtraBold

@Composable
fun IeumsaeTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = C.Blue,
            onPrimary = Color.White,
            background = C.Bg,
            onBackground = C.Fg,
            surface = C.Bg,
            onSurface = C.Fg,
            error = C.Red,
            outline = C.Line,
        ),
        typography = Typography(
            headlineLarge = TextStyle(fontSize = 30.sp, fontWeight = Bold, lineHeight = 40.sp, letterSpacing = (-0.4).sp),
            headlineMedium = TextStyle(fontSize = 27.sp, fontWeight = Bold, lineHeight = 37.sp, letterSpacing = (-0.4).sp),
            titleLarge = TextStyle(fontSize = 20.sp, fontWeight = Bold),
            titleMedium = TextStyle(fontSize = 17.sp, fontWeight = Bold),
            bodyLarge = TextStyle(fontSize = 17.sp, lineHeight = 25.sp),
            bodyMedium = TextStyle(fontSize = 15.sp, lineHeight = 22.sp),
            labelLarge = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.Bold),
        ),
        content = content,
    )
}
