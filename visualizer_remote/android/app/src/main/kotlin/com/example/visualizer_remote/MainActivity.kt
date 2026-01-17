package com.example.visualizer_remote

import android.content.Intent
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import com.example.visualizer_remote.audio.AudioCaptureChannel

class MainActivity : FlutterActivity() {

    private lateinit var audioChannel: AudioCaptureChannel

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        audioChannel = AudioCaptureChannel(this, flutterEngine)
        audioChannel.attach()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        audioChannel.onActivityResult(requestCode, resultCode, data)
    }
}
