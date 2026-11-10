package kr.ieumsae.app

import android.app.Application
import android.content.Context
import kr.ieumsae.app.data.Api
import kr.ieumsae.app.data.Session

class IeumsaeApp : Application() {
    val api by lazy { Api() }
    val session by lazy { Session(this, api) }
}

val Context.app: IeumsaeApp get() = applicationContext as IeumsaeApp
