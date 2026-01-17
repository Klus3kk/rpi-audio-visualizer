package com.example.visualizer_remote.audio

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

private const val EXTRA_DATA = "extra_data"
private const val EXTRA_IP = "extra_ip"
private const val EXTRA_PORT = "extra_port"


class AudioCaptureChannel(
    private val activity: Activity,
    private val engine: FlutterEngine
) {

    companion object {
        const val CH_NAME = "visualizer/audio_capture"
        const val REQ_CAPTURE = 1337
    }

    private val mgr =
        activity.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager

    private var pendingIp: String = "192.168.1.10"
    private var pendingPort: Int = 7777

    fun attach() {
        MethodChannel(engine.dartExecutor.binaryMessenger, CH_NAME)
            .setMethodCallHandler { call: MethodCall, result: MethodChannel.Result ->
                when (call.method) {
                    "start" -> {
                        pendingIp = call.argument<String>("ip") ?: pendingIp
                        pendingPort = call.argument<Int>("port") ?: pendingPort
                        val intent = mgr.createScreenCaptureIntent()
                        activity.startActivityForResult(intent, REQ_CAPTURE)
                        result.success(null)
                    }

                    "stop" -> {
                        activity.stopService(
                            Intent(activity, AudioCaptureService::class.java)
                        )
                        result.success(null)
                    }

                    else -> result.notImplemented()
                }
            }
    }

    fun onActivityResult(req: Int, res: Int, data: Intent?) {
        if (req != REQ_CAPTURE || res != Activity.RESULT_OK || data == null) return

        val i = Intent(activity, AudioCaptureService::class.java).apply {
            putExtra(AudioCaptureService.EXTRA_RESULT_CODE, res)
            putExtra(AudioCaptureService.EXTRA_RESULT_DATA, data)
        // opcjonalnie: ip/port – dodaj stałe w service jeśli chcesz używać
        }
        activity.startForegroundService(i)

    }
}
