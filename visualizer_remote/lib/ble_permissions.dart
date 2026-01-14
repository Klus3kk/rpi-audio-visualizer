import 'dart:io';
import 'package:permission_handler/permission_handler.dart';

class BlePermissions {
  static Future<bool> hasPermissions() async {
    if (Platform.isAndroid) {
      if (await Permission.bluetoothScan.isGranted &&
          await Permission.bluetoothConnect.isGranted) {
        return true;
      }
      // fallback for older Android
      if (await Permission.location.isGranted) {
        return true;
      }
      return false;
    }
    return true;
  }

  static Future<bool> request() async {
    if (Platform.isAndroid) {
      final results = await [
        Permission.bluetoothScan,
        Permission.bluetoothConnect,
        Permission.location,
      ].request();

      return results.values.any((r) => r.isGranted);
    }
    return true;
  }
}
