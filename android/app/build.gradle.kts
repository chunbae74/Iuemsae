import java.util.Properties
import java.net.URI

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}


val serverKeys = Properties().apply {
    val f = rootProject.file("server-keys.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

fun quoted(v: String) = "\"" + v.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

val apiBaseUrl = providers.gradleProperty("ieumsae.apiBaseUrl").orElse(providers.environmentVariable("IEUMSAE_API_BASE_URL")).get()
val cloudProjectNumber = providers.gradleProperty("ieumsae.cloudProjectNumber").orElse(providers.environmentVariable("IEUMSAE_CLOUD_PROJECT_NUMBER")).get()
require(URI(apiBaseUrl).scheme == "https" && URI(apiBaseUrl).host != null)
require(cloudProjectNumber.toLong() > 0)
require(serverKeys.getProperty("tlsPin", "").matches(Regex("sha256/[A-Za-z0-9+/]{43}=")))
require(serverKeys.getProperty("sttSigningPublicKey", "").isNotBlank())
require(serverKeys.getProperty("sttSigningKeyId", "").isNotBlank())

android {
    namespace = "kr.ieumsae.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "kr.ieumsae.app"

        minSdk = 29
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
        manifestPlaceholders["appLabel"] = "@string/app_name"

        buildConfigField("String", "API_BASE_URL", quoted(apiBaseUrl))
        buildConfigField("long", "CLOUD_PROJECT_NUMBER", "${cloudProjectNumber}L")
        buildConfigField("String", "STT_SIGNING_KEY_ID", quoted(serverKeys.getProperty("sttSigningKeyId", "")))
        buildConfigField("String", "STT_SIGNING_PUBLIC_KEY", quoted(serverKeys.getProperty("sttSigningPublicKey", "")))
        buildConfigField("String", "TLS_PIN", quoted(serverKeys.getProperty("tlsPin", "")))
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.okhttp)
    implementation(libs.tink.android)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.play.integrity)
    debugImplementation(libs.androidx.ui.tooling)

    testImplementation(libs.junit)
}
