package kr.ieumsae.app.data


object PasswordRules {
    data class Rule(val label: String, val met: Boolean)

    fun evaluate(password: String, loginId: String): List<Rule> {
        val length = password.codePointCount(0, password.length)
        val kinds = listOf("[a-z]", "[A-Z]", "[0-9]", "[^A-Za-z0-9]")
            .count { Regex(it).containsMatchIn(password) }
        val id = loginId.trim().lowercase()
        return listOf(
            Rule("3종류 조합 시 8자 이상 또는 2종류 조합 시 10자 이상", (kinds >= 3 && length >= 8) || (kinds >= 2 && length >= 10)),
            Rule("최대 64자", length in 1..64),
            Rule("같은 문자 4회 연속 사용하지 않기", password.isNotEmpty() && !Regex("(.)\\1\\1\\1").containsMatchIn(password)),
            Rule("아이디 포함하지 않기", password.isNotEmpty() && id.isNotEmpty() && !password.lowercase().contains(id)),
        )
    }
}
