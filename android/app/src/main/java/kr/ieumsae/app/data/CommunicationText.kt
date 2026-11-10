package kr.ieumsae.app.data


object CommunicationText {

    val speechOptions = listOf(
        1 to "조금 불편해요",
        2 to "알아듣기 어려울 수 있어요",
        3 to "많이 어려워요",
    )
    val comprehensionOptions = listOf(
        1 to "도움 없이 이해해요",
        2 to "천천히 말해 주면 이해해요",
        3 to "쉬운 말로 설명해 주면 이해해요",
    )

    private val comprehensionForListener = mapOf(
        1 to "편하게 말씀해주세요",
        2 to "천천히 말해 주세요",
        3 to "쉬운 말로 천천히 설명해 주세요",
    )


    fun forListener(c: Communication?): String? {
        if (c == null || !c.showToListener) return null
        val parts = listOfNotNull(
            c.comprehensionLevel?.let(comprehensionForListener::get),
        )
        return parts.takeIf { it.isNotEmpty() }?.joinToString(" · ")
    }
}
