// visualizer_remote/android/app/src/main/kotlin/com/example/visualizer_remote/MediaListener.kt

package com.example.visualizer_remote

import android.content.ComponentName
import android.content.Context
import android.media.MediaMetadata
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.util.Log

/**
 * Listens to active media sessions (Spotify, YouTube Music, etc.)
 * and extracts: artist, title, album, albumArtUri
 */
class MediaListener(private val context: Context) {

    companion object {
        const val TAG = "MediaListener"
    }

    private var sessionManager: MediaSessionManager? = null
    private var activeController: MediaController? = null
    
    data class MediaInfo(
        val artist: String = "",
        val title: String = "",
        val album: String = "",
        val coverUrl: String = ""
    )

    var onMediaChanged: ((MediaInfo) -> Unit)? = null

    fun start() {
        sessionManager = context.getSystemService(Context.MEDIA_SESSION_SERVICE) as MediaSessionManager

        val listener = object : MediaSessionManager.OnActiveSessionsChangedListener {
            override fun onActiveSessionsChanged(controllers: List<MediaController>?) {
                Log.d(TAG, "Active sessions changed: ${controllers?.size ?: 0}")
                updateActiveController(controllers)
            }
        }

        try {
            // Request notification listener permission first!
            val component = ComponentName(context, NotificationListener::class.java)
            val controllers = sessionManager?.getActiveSessions(component)
            updateActiveController(controllers)
            sessionManager?.addOnActiveSessionsChangedListener(listener, component)
        } catch (e: SecurityException) {
            Log.e(TAG, "Missing notification listener permission: $e")
        }
    }

    fun stop() {
        activeController?.unregisterCallback(callback)
        activeController = null
    }

    private fun updateActiveController(controllers: List<MediaController>?) {
        activeController?.unregisterCallback(callback)
        
        // Pick first active controller (usually current playing app)
        activeController = controllers?.firstOrNull()
        
        if (activeController != null) {
            Log.d(TAG, "Active controller: ${activeController?.packageName}")
            activeController?.registerCallback(callback)
            notifyMetadata(activeController?.metadata)
        } else {
            Log.d(TAG, "No active media controller")
            onMediaChanged?.invoke(MediaInfo())
        }
    }

    private val callback = object : MediaController.Callback() {
        override fun onMetadataChanged(metadata: MediaMetadata?) {
            Log.d(TAG, "Metadata changed")
            notifyMetadata(metadata)
        }

        override fun onPlaybackStateChanged(state: PlaybackState?) {
            Log.d(TAG, "Playback state: ${state?.state}")
        }
    }

    private fun notifyMetadata(metadata: MediaMetadata?) {
        if (metadata == null) {
            onMediaChanged?.invoke(MediaInfo())
            return
        }

        val artist = metadata.getString(MediaMetadata.METADATA_KEY_ARTIST) ?: ""
        val title = metadata.getString(MediaMetadata.METADATA_KEY_TITLE) ?: ""
        val album = metadata.getString(MediaMetadata.METADATA_KEY_ALBUM) ?: ""

        Log.d(TAG, "NOW PLAYING: $artist - $title [$album]")

        onMediaChanged?.invoke(MediaInfo(
            artist = artist,
            title = title,
            album = album,
            coverUrl = ""  // Not used
        ))
    }
}