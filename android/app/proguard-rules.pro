-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class kr.ieumsae.app.** {
    *** Companion;
}
-keepclasseswithmembers class kr.ieumsae.app.** {
    kotlinx.serialization.KSerializer serializer(...);
}


-dontwarn com.google.errorprone.annotations.**
-dontwarn javax.annotation.**
-dontwarn com.google.api.client.http.**
-dontwarn org.joda.time.Instant


-assumenosideeffects class android.util.Log {
    public static *** d(...);
    public static *** v(...);
    public static *** i(...);
}
