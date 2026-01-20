// visualizer_remote/lib/media_listener.dart
import 'dart:io';
import 'package:flutter/services.dart';

class MediaInfo {
  final String artist;
  final String title;
  final String album;
  final String coverUrl;

  MediaInfo({
    this.artist = '',
    this.title = '',
    this.album = '',
    this.coverUrl = '',
  });
}

class MediaListener {
  static const _channel = MethodChannel('visualizer/media_listener');
  
  Function(MediaInfo)? onMediaChanged;

  MediaListener(dynamic context) {
    if (!Platform.isAndroid) return;
    
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'onMediaChanged') {
        final args = call.arguments as Map;
        final info = MediaInfo(
          artist: args['artist'] ?? '',
          title: args['title'] ?? '',
          album: args['album'] ?? '',
          coverUrl: args['coverUrl'] ?? '',
        );
        onMediaChanged?.call(info);
      }
    });
  }

  Future<void> start() async {
    if (!Platform.isAndroid) return;
    try {
      await _channel.invokeMethod('start');
    } catch (e) {
      print('MediaListener.start error: $e');
    }
  }

  Future<void> stop() async {
    if (!Platform.isAndroid) return;
    try {
      await _channel.invokeMethod('stop');
    } catch (e) {
      print('MediaListener.stop error: $e');
    }
  }
}