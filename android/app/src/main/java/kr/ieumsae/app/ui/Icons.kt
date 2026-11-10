package kr.ieumsae.app.ui

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp


object Ic {
    private fun line(vararg d: String, width: Float = 2f): ImageVector =
        ImageVector.Builder(defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f)
            .apply {
                d.forEach {
                    addPath(
                        pathData = PathParser().parsePathString(it).toNodes(),
                        stroke = SolidColor(Color.Black),
                        strokeLineWidth = width,
                        strokeLineCap = StrokeCap.Round,
                        strokeLineJoin = StrokeJoin.Round,
                    )
                }
            }
            .build()

    val Mic = line("M12,3a3,3 0 0 1 3,3v5a3,3 0 0 1 -6,0v-5a3,3 0 0 1 3,-3z", "M5.5,11a6.5,6.5 0 0 0 13,0M12,17.5V21")
    val Back = line("M15,5l-7,7 7,7")
    val Chevron = line("M9,5l7,7 -7,7")
    val Speaker = line("M4,9.5h3.5L12,6v12l-4.5,-3.5H4z", "M15.5,9a4.2,4.2 0 0 1 0,6M18,6.5a8,8 0 0 1 0,11")
    val Rotate = line("M19.5,10A8,8 0 0 0 5.6,7.2M4.5,3.5v4h4M4.5,14a8,8 0 0 0 13.9,2.8M19.5,20.5v-4h-4")
    val Chat = line("M12,4.5c4.7,0 8.5,3.1 8.5,7s-3.8,7 -8.5,7c-1,0 -1.9,-0.1 -2.8,-0.4L4.5,20l1.3,-3.7C4.4,15 3.5,13.3 3.5,11.5c0,-3.9 3.8,-7 8.5,-7z")
    val Sliders = line(
        "M4,7h9M17,7h3M4,12h3M11,12h9M4,17h11M19,17h1",
        "M13,7a2,2 0 1 0 4,0a2,2 0 1 0 -4,0",
        "M7,12a2,2 0 1 0 4,0a2,2 0 1 0 -4,0",
        "M15,17a2,2 0 1 0 4,0a2,2 0 1 0 -4,0",
    )
    val Backspace = line("M9,6h11v12H9l-6,-6z", "M12.5,10l4,4M16.5,10l-4,4")
    val Enter = line("M19,6v5a3,3 0 0 1 -3,3H5", "M9,10l-4,4 4,4")
    val Arrow = line("M5,12h14M13,6l6,6 -6,6")
    val Check = line("M5,12.5l4.5,4.5L19,7.5", width = 3f)
}
