package com.example.visualizer_remote.audio

import android.app.Activity
import android.content.ComponentName
import android.content.Context
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.service.notification.NotificationListenerService
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * MediaListenerChannel - Listens to Bluetooth media metadata
 * Requires: BIND_NOTIFICATION_LISTENER_SERVICE permission in AndroidManifest
 */
class MediaListenerChannel(
    private val activity: Activity,
    private val engine: FlutterEngine
) {
    companion object {
        const val CHANNEL_NAME = "visualizer/media_listener"
    }

    private var mediaSessionManager: MediaSessionManager? = null
    private var channel: MethodChannel? = null
    private var activeController: MediaController? = null
    
    private val callback = object : MediaController.Callback() {
        override fun onMetadataChanged(metadata: android.media.MediaMetadata?) {
            sendMetadata(metadata)
        }

        override fun onPlaybackStateChanged(state: PlaybackState?) {
            // Optional: track play/pause state
        }
    }

    fun attach() {
        channel = MethodChannel(engine.dartExecutor.binaryMessenger, CHANNEL_NAME)
        channel?.setMethodCallHandler { call: MethodCall, result: MethodChannel.Result ->
            when (call.method) {
                "start" -> {
                    startListening()
                    result.success(null)
                }
                "stop" -> {
                    stopListening()
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun startListening() {
        try {
            mediaSessionManager = activity.getSystemService(Context.MEDIA_SESSION_SERVICE) 
                as? MediaSessionManager
            
            val componentName = ComponentName(activity, MediaNotificationListener::class.java)
            
            // Get active sessions
            val controllers = mediaSessionManager?.getActiveSessions(componentName) ?: emptyList()
            
            // Find first controller (usually BT or media player)
            activeController = controllers.firstOrNull()
            activeController?.registerCallback(callback)
            
            // Send initial metadata
            sendMetadata(activeController?.metadata)
            
        } catch (e: SecurityException) {
            // Need notification listener permission
            android.util.Log.e("MediaListener", "Permission denied: $e")
        } catch (e: Exception) {
            android.util.Log.e("MediaListener", "Error starting: $e")
        }
    }

    private fun stopListening() {
        activeController?.unregisterCallback(callback)
        activeController = null
    }

    private fun sendMetadata(metadata: android.media.MediaMetadata?) {
        if (metadata == null) return
        
        val data = hashMapOf<String, String>(
            "artist" to (metadata.getString(android.media.MediaMetadata.METADATA_KEY_ARTIST) ?: ""),
            "title" to (metadata.getString(android.media.MediaMetadata.METADATA_KEY_TITLE) ?: ""),
            "album" to (metadata.getString(android.media.MediaMetadata.METADATA_KEY_ALBUM) ?: ""),
            "coverUrl" to ""  // Album art would need bitmap processing
        )
        
        activity.runOnUiThread {
            channel?.invokeMethod("onMediaChanged", data)
        }
    }
}

/**
 * Notification Listener Service (required for media session access)
 * User must enable this in Settings > Notification Access
 */
class MediaNotificationListener : NotificationListenerService() {
    override fun onListenerConnected() {
        super.onListenerConnected()
        android.util.Log.d("MediaListener", "Notification listener connected")
    }
}