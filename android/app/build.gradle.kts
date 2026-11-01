plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Версия берётся из общего файла версии программы (pglmocap/__init__.py), номер сборки — из CI
val appVersion: String = run {
    val f = rootProject.file("../pglmocap/__init__.py")
    Regex("__version__ = \"([^\"]+)\"").find(f.readText())?.groupValues?.get(1) ?: "1.0.0"
}
val buildNumber: Int = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()

android {
    namespace = "com.pgl.mocap"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.pgl.mocap"
        minSdk = 26
        targetSdk = 35
        versionCode = buildNumber
        versionName = "$appVersion-build$buildNumber"
        // MediaPipe для Android поставляется только под 64-битный ARM
        ndk { abiFilters += "arm64-v8a" }
    }

    signingConfigs {
        create("release") {
            storeFile = rootProject.file("keystore/pgl-mocap.jks")
            storePassword = "pglmocap"
            keyAlias = "pglmocap"
            keyPassword = "pglmocap"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
        debug {
            signingConfig = signingConfigs.getByName("release")
        }
    }

    androidResources {
        noCompress += "task"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")

    val camerax = "1.4.1"
    implementation("androidx.camera:camera-core:$camerax")
    implementation("androidx.camera:camera-camera2:$camerax")
    implementation("androidx.camera:camera-lifecycle:$camerax")

    implementation("com.google.mediapipe:tasks-vision:0.10.14")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}

tasks.withType<Test> {
    testLogging {
        events("passed", "failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
