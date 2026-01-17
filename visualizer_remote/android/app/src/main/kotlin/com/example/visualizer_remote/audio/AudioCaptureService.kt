package com.example.visualizer_remote.audio

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.example.visualizer_remote.R

class AudioCaptureService : Service() {

    companion object {
        const val TAG = "AudioCaptureService"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
        const val NOTIF_CH = "viz_capture"
        const val NOTIF_ID = 1001
    }

    private var projection: MediaProjection? = null

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "onCreate")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "onStartCommand intent=$intent")

        ensureNotifChannel()
        startForeground(NOTIF_ID, buildNotif("Capturing audio…"))

        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, 0) ?: 0
        val resultData: Intent? = intent?.getParcelableExtra(EXTRA_RESULT_DATA)

        if (resultCode == 0 || resultData == null) {
            Log.e(TAG, "Missing MediaProjection permission data -> stopping")
            stopSelf()
            return START_NOT_STICKY
        }

        val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        projection = mpm.getMediaProjection(resultCode, resultData)

        Log.i(TAG, "MediaProjection acquired OK: $projection")

        // TODO: tutaj potem wstawimy AudioRecord z AudioPlaybackCaptureConfiguration
        // i stream do Fluttera/UDP itp.

        return START_STICKY
    }

    override fun onDestroy() {
        Log.i(TAG, "onDestroy")
        try { projection?.stop() } catch (_: Exception) {}
        projection = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun ensureNotifChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
            if (nm.getNotificationChannel(NOTIF_CH) == null) {
                nm.createNotificationChannel(
                    NotificationChannel(
                        NOTIF_CH,
                        "Visualizer Capture",
                        NotificationManager.IMPORTANCE_LOW
                    )
                )
            }
        }
    }

    private fun buildNotif(text: String): Notification {
        return NotificationCompat.Builder(this, NOTIF_CH)
            .setContentTitle("Visualizer")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .build()
    }
}
