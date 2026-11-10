package kr.ieumsae.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun ComprehensionNotice(text: String) {
    Column(Modifier.fillMaxWidth().background(Color(0xFFF0E8FA), RoundedCornerShape(14.dp)).padding(18.dp)) {
        Text("저와 대화할 때", color = Color(0xFF593681), fontSize = 16.sp, fontWeight = FontWeight.Bold)
        Text(text, color = Color(0xFF392052), fontSize = 22.sp, lineHeight = 32.sp,
            fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 8.dp))
    }
}
