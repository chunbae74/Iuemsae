package kr.ieumsae.app.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kr.ieumsae.app.R

@Composable
fun Logo(size: Dp) {

    Box(Modifier.size(size)) {
        Image(
            painterResource(R.drawable.ic_launcher_foreground),
            contentDescription = null,
            modifier = Modifier.size(size * 1.55f).align(Alignment.Center),
        )
    }
}

@Composable
fun AppHeader(title: String? = "이음새", onBack: (() -> Unit)? = null, trailing: @Composable () -> Unit = {}) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 56.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (onBack != null) {
            IconButton(onClick = onBack, modifier = Modifier.padding(start = 0.dp)) {
                Icon(Ic.Back, contentDescription = "뒤로", tint = C.Fg)
            }
        } else if (title == "이음새") {
            Logo(30.dp)
            Spacer(Modifier.width(8.dp))
        }
        if (title != null) Text(title, fontSize = 20.sp, fontWeight = FontWeight.ExtraBold)
        Spacer(Modifier.weight(1f))
        trailing()
    }
}

@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, loading: Boolean = false) {
    Button(
        onClick = onClick,
        enabled = enabled && !loading,
        modifier = modifier.fillMaxWidth().heightIn(min = 60.dp),
        shape = RoundedCornerShape(14.dp),
        colors = ButtonDefaults.buttonColors(containerColor = C.Blue, disabledContainerColor = C.Blue.copy(alpha = 0.55f), disabledContentColor = Color.White),
    ) {
        if (loading) CircularProgressIndicator(Modifier.size(24.dp), color = Color.White, strokeWidth = 3.dp)
        else Text(text, fontSize = 18.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun GhostButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, color: Color = C.Fg, container: Color = C.Soft) {
    Button(
        onClick = onClick,
        modifier = modifier.heightIn(min = 56.dp),
        shape = RoundedCornerShape(14.dp),
        colors = ButtonDefaults.buttonColors(containerColor = container, contentColor = color),
    ) { Text(text, fontSize = 17.sp, fontWeight = FontWeight.Bold) }
}

@Composable
fun LinkButton(text: String, onClick: () -> Unit) {
    TextButton(onClick = onClick, contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)) {
        Text(text, color = Color(0xFF4B5160), fontSize = 15.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
fun Field(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    password: Boolean = false,
    keyboard: KeyboardType = KeyboardType.Text,
    placeholder: String? = null,
) {
    var show by remember { mutableStateOf(false) }
    Column(modifier.fillMaxWidth()) {
        Text(label, fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Color(0xFF4B5160))
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = value,
            onValueChange = onChange,
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
            textStyle = androidx.compose.ui.text.TextStyle(fontSize = 18.sp),
            shape = RoundedCornerShape(14.dp),
            placeholder = placeholder?.let { { Text(it, color = C.Muted) } },
            visualTransformation = if (password && !show) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(
                keyboardType = if (password) KeyboardType.Password else keyboard,
                autoCorrectEnabled = false,
            ),
            trailingIcon = if (password) {
                {
                    TextButton(onClick = { show = !show }, modifier = Modifier.padding(end = 4.dp)) {
                        Text(if (show) "숨기기" else "보기", color = Color(0xFF1D4ED8), fontWeight = FontWeight.Bold)
                    }
                }
            } else null,
            colors = OutlinedTextFieldDefaults.colors(unfocusedBorderColor = C.Line, focusedBorderColor = C.Blue),
        )
    }
}

@Composable
fun ErrorText(text: String?) {
    if (text != null) Text(text, color = C.Red, fontSize = 15.sp, modifier = Modifier.padding(top = 12.dp))
}

@Composable
fun InfoCard(text: String) {
    androidx.compose.material3.Surface(
        color = C.Soft,
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth(),
    ) { Text(text, Modifier.padding(16.dp), color = C.Muted, fontSize = 15.sp, lineHeight = 22.sp) }
}

@Composable
fun SpacedColumn(modifier: Modifier = Modifier, gap: Dp = 18.dp, content: @Composable () -> Unit) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(gap)) { content() }
}
