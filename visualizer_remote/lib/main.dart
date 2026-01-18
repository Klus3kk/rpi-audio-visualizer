import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:permission_handler/permission_handler.dart';

// ===================== BLE UUIDs =====================
const String kDeviceName = 'Visualizer';

const String kSvc = '12345678-1234-5678-1234-56789abcdef0';
const String kCmd = '12345678-1234-5678-1234-56789abcdef9';   // WRITE
const String kState = '12345678-1234-5678-1234-56789abcdef8'; // READ/NOTIFY (opcjonalne)

// ===================== UI theme =====================
class Retro {
  static const bg = Color(0xFF101114);
  static const panel = Color(0xFF1B1D22);
  static const edge = Color(0xFF30333B);
  static const yellow = Color(0xFFFFD166);
  static const ok = Color(0xFF4AF2A1);
  static const bad = Color(0xFFFF4D6D);
}

void main() => runApp(const VisualizerRemoteApp());

class VisualizerRemoteApp extends StatelessWidget {
  const VisualizerRemoteApp({super.key});

  @override
  Widget build(BuildContext context) {
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xFF8B8B8B),
        brightness: Brightness.dark,
      ),
    );

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Visualizer',
      theme: base.copyWith(
        scaffoldBackgroundColor: Retro.bg,
        textTheme: GoogleFonts.vt323TextTheme(base.textTheme).apply(
          bodyColor: Colors.white,
          displayColor: Colors.white,
        ),
      ),
      home: const PermissionGate(),
    );
  }
}

// ===================== Permissions =====================
class PermissionGate extends StatefulWidget {
  const PermissionGate({super.key});

  @override
  State<PermissionGate> createState() => _PermissionGateState();
}

class _PermissionGateState extends State<PermissionGate> {
  bool _ok = false;

  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    final ok = await _hasBlePerms();
    setState(() => _ok = ok);
  }

  Future<bool> _hasBlePerms() async {
    if (!Platform.isAndroid) return true;
    final scan = await Permission.bluetoothScan.isGranted;
    final conn = await Permission.bluetoothConnect.isGranted;
    if (scan && conn) return true;
    final loc = await Permission.location.isGranted;
    return loc;
  }

  Future<void> _request() async {
    if (!Platform.isAndroid) {
      setState(() => _ok = true);
      return;
    }

    final results = await [
      Permission.bluetoothScan,
      Permission.bluetoothConnect,
      Permission.location,
    ].request();

    setState(() => _ok = results.values.any((r) => r.isGranted));
  }

  @override
  Widget build(BuildContext context) {
    if (_ok) return const Root();

    return Scaffold(
      backgroundColor: Retro.bg,
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: CutPanel(
            cut: 16,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.bluetooth, size: 64, color: Retro.yellow),
                const SizedBox(height: 12),
                const Text('BLUETOOTH REQUIRED', style: TextStyle(fontSize: 26, letterSpacing: 2)),
                const SizedBox(height: 10),
                const Text(
                  'App needs Bluetooth permissions to control your Visualizer (RPi).',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 18, color: Colors.white70),
                ),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton(
                    onPressed: _request,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.black.withOpacity(0.25),
                      foregroundColor: Retro.yellow,
                      shape: const BeveledRectangleBorder(),
                      side: BorderSide(color: Retro.yellow.withOpacity(0.65), width: 2),
                    ),
                    child: const Text('ENABLE', style: TextStyle(letterSpacing: 2, fontSize: 18)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ===================== Data model =====================
class VizState {
  final String mode; // mic | bt
  final String effect;
  final double brightness;
  final double intensity;
  final double gain;
  final double smoothing;
  final String deviceAddr; // MAC for BlueALSA A2DP (optional but recommended)
  final String artist;
  final String title;

  const VizState({
    required this.mode,
    required this.effect,
    required this.brightness,
    required this.intensity,
    required this.gain,
    required this.smoothing,
    required this.deviceAddr,
    required this.artist,
    required this.title,
  });

  factory VizState.initial() => const VizState(
        mode: 'mic',
        effect: 'bars',
        brightness: 0.55,
        intensity: 0.75,
        gain: 1.0,
        smoothing: 0.65,
        deviceAddr: 'BC:A0:80:E0:B9:4E', // ustaw domyślnie swój telefon (możesz zmienić w UI)
        artist: '',
        title: '',
      );

  VizState copyWith({
    String? mode,
    String? effect,
    double? brightness,
    double? intensity,
    double? gain,
    double? smoothing,
    String? deviceAddr,
    String? artist,
    String? title,
  }) {
    return VizState(
      mode: mode ?? this.mode,
      effect: effect ?? this.effect,
      brightness: brightness ?? this.brightness,
      intensity: intensity ?? this.intensity,
      gain: gain ?? this.gain,
      smoothing: smoothing ?? this.smoothing,
      deviceAddr: deviceAddr ?? this.deviceAddr,
      artist: artist ?? this.artist,
      title: title ?? this.title,
    );
  }

  Map<String, dynamic> toJson() => {
        'mode': mode,
        'effect': effect,
        'brightness': brightness,
        'intensity': intensity,
        'gain': gain,
        'smoothing': smoothing,
        'device_addr': deviceAddr,
        'artist': artist,
        'title': title,
        'connected': true,
        'device_name': 'phone',
      };

  static VizState fromJson(Map<String, dynamic> j, {VizState? fallback}) {
    final fb = fallback ?? VizState.initial();
    double d(dynamic v, double def) {
      if (v == null) return def;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString()) ?? def;
    }

    return VizState(
      mode: (j['mode'] ?? fb.mode).toString(),
      effect: (j['effect'] ?? fb.effect).toString(),
      brightness: d(j['brightness'], fb.brightness).clamp(0.0, 1.0),
      intensity: d(j['intensity'], fb.intensity).clamp(0.0, 1.0),
      gain: d(j['gain'], fb.gain).clamp(0.1, 6.0),
      smoothing: d(j['smoothing'], fb.smoothing).clamp(0.0, 0.95),
      deviceAddr: (j['device_addr'] ?? fb.deviceAddr).toString(),
      artist: (j['artist'] ?? fb.artist).toString(),
      title: (j['title'] ?? fb.title).toString(),
    );
  }
}

// ===================== BLE Controller =====================
enum ConnStatus { idle, scanning, connecting, connected, error }

class BleController {
  BluetoothDevice? device;
  BluetoothCharacteristic? chCmd;
  BluetoothCharacteristic? chState;

  StreamSubscription? _scanSub;
  StreamSubscription? _connSub;
  StreamSubscription? _notifySub;

  final ValueNotifier<ConnStatus> status = ValueNotifier(ConnStatus.idle);
  final ValueNotifier<String?> error = ValueNotifier(null);

  final ValueNotifier<VizState> desired = ValueNotifier(VizState.initial());
  final ValueNotifier<VizState> remote = ValueNotifier(VizState.initial());

  DateTime _lastScanAt = DateTime.fromMillisecondsSinceEpoch(0);
  bool _scanInFlight = false;

  Future<void> scanAndConnect({Duration timeout = const Duration(seconds: 6)}) async {
    if (_scanInFlight) return;

    final now = DateTime.now();
    if (now.difference(_lastScanAt) < const Duration(seconds: 2)) return;
    _lastScanAt = now;

    error.value = null;
    status.value = ConnStatus.scanning;
    _scanInFlight = true;

    try {
      await FlutterBluePlus.stopScan();
    } catch (_) {}

    await FlutterBluePlus.startScan(timeout: timeout);

    _scanSub?.cancel();
    _scanSub = FlutterBluePlus.scanResults.listen((results) async {
      for (final r in results) {
        final name = r.device.platformName;
        final matchesName = name == kDeviceName;

        // FIX: Guid -> String
        final advUuids = r.advertisementData.serviceUuids
            .map((g) => g.toString().toLowerCase())
            .toList();
        final matchesSvc = advUuids.contains(kSvc.toLowerCase());

        if (matchesName || matchesSvc) {
          try {
            await FlutterBluePlus.stopScan();
          } catch (_) {}
          await _connect(r.device);
          return;
        }
      }
    });

    Future.delayed(timeout + const Duration(milliseconds: 200), () {
      if (status.value == ConnStatus.scanning) {
        status.value = ConnStatus.error;
        error.value = 'Visualizer not found';
      }
      _scanInFlight = false;
    });
  }

  Future<void> _connect(BluetoothDevice d) async {
    status.value = ConnStatus.connecting;
    device = d;
    error.value = null;

    try {
      await d.connect(autoConnect: false, timeout: const Duration(seconds: 8));
    } catch (_) {}

    _connSub?.cancel();
    _connSub = d.connectionState.listen((s) {
      final ok = (s == BluetoothConnectionState.connected);
      if (!ok) {
        status.value = ConnStatus.error;
        error.value ??= 'Disconnected';
      }
    });

    try {
      await _discover(d);
      await _enableNotifyIfPresent();
      status.value = ConnStatus.connected;

      await sendFullState(desired.value);
    } catch (e) {
      status.value = ConnStatus.error;
      error.value = 'BLE init failed: $e';
    } finally {
      _scanInFlight = false;
    }
  }

  Future<void> _discover(BluetoothDevice d) async {
    final services = await d.discoverServices();
    final svc = services.where((s) => s.uuid.toString().toLowerCase() == kSvc.toLowerCase()).toList();
    if (svc.isEmpty) throw Exception('GATT service not found ($kSvc)');
    final s = svc.first;

    BluetoothCharacteristic? pick(String uuid) {
      final u = uuid.toLowerCase();
      for (final c in s.characteristics) {
        if (c.uuid.toString().toLowerCase() == u) return c;
      }
      return null;
    }

    chCmd = pick(kCmd);
    chState = pick(kState);

    if (chCmd == null) throw Exception('CMD characteristic missing ($kCmd)');
  }

  Future<void> _enableNotifyIfPresent() async {
    final ch = chState;
    if (ch == null) return;

    await ch.setNotifyValue(true);
    _notifySub?.cancel();
    _notifySub = ch.lastValueStream.listen((bytes) {
      try {
        final txt = utf8.decode(bytes);
        final j = jsonDecode(txt);
        if (j is Map<String, dynamic>) {
          remote.value = VizState.fromJson(j, fallback: remote.value);
        }
      } catch (_) {}
    });
  }

  Future<void> disconnect() async {
    try {
      await FlutterBluePlus.stopScan();
    } catch (_) {}

    await _scanSub?.cancel();
    await _notifySub?.cancel();
    await _connSub?.cancel();
    _scanSub = null;
    _notifySub = null;
    _connSub = null;

    final d = device;
    device = null;
    chCmd = null;
    chState = null;

    if (d != null) {
      try {
        await d.disconnect();
      } catch (_) {}
    }

    status.value = ConnStatus.idle;
    error.value = null;
    _scanInFlight = false;
  }

  Future<void> sendPatch(Map<String, dynamic> patch) async {
    final ch = chCmd;
    if (ch == null) return;

    final payload = utf8.encode(jsonEncode(patch));
    final canNoResp = ch.properties.writeWithoutResponse;
    await ch.write(payload, withoutResponse: canNoResp);
  }

  Future<void> sendFullState(VizState s) async {
    await sendPatch(s.toJson());
  }
}

// ===================== UI =====================
class Root extends StatefulWidget {
  const Root({super.key});
  @override
  State<Root> createState() => _RootState();
}

class _RootState extends State<Root> {
  final BleController ble = BleController();
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    ble.scanAndConnect();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    ble.disconnect();
    super.dispose();
  }

  void _debounced(Duration d, VoidCallback f) {
    _debounce?.cancel();
    _debounce = Timer(d, f);
  }

  Widget _plate(String t, {Color accent = Retro.yellow}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.black.withOpacity(0.25),
        border: Border.all(color: accent.withOpacity(0.6), width: 1.5),
      ),
      child: Text(
        t.toUpperCase(),
        style: TextStyle(color: accent, letterSpacing: 2, fontSize: 14),
        overflow: TextOverflow.ellipsis,
      ),
    );
  }

  Widget _btn(String text, {required VoidCallback? onPressed, Color fg = Retro.yellow, Color border = Retro.yellow}) {
    return SizedBox(
      height: 46,
      child: ElevatedButton(
        onPressed: onPressed,
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.black.withOpacity(0.25),
          foregroundColor: fg,
          shape: const BeveledRectangleBorder(),
          side: BorderSide(color: border.withOpacity(0.65), width: 2),
        ),
        child: Text(text, style: const TextStyle(letterSpacing: 2, fontSize: 18)),
      ),
    );
  }

  Widget _slider(String label, double value, double min, double max, ValueChanged<double> onChanged) {
    final v = value.clamp(min, max);
    return Column(
      children: [
        Row(
          children: [
            Expanded(child: Text(label.toUpperCase(), style: const TextStyle(letterSpacing: 2, fontSize: 16))),
            Text(v.toStringAsFixed(2), style: const TextStyle(fontSize: 16)),
          ],
        ),
        SliderTheme(
          data: SliderTheme.of(context).copyWith(
            trackHeight: 10,
            thumbShape: const RectThumbShape(),
            overlayShape: SliderComponentShape.noOverlay,
            activeTrackColor: Retro.yellow.withOpacity(0.9),
            inactiveTrackColor: Colors.white.withOpacity(0.18),
            thumbColor: Retro.yellow,
          ),
          child: Slider(value: v, min: min, max: max, onChanged: onChanged),
        ),
        const SizedBox(height: 8),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<ConnStatus>(
      valueListenable: ble.status,
      builder: (context, st, _) {
        return ValueListenableBuilder<String?>(
          valueListenable: ble.error,
          builder: (context, err, __) {
            return ValueListenableBuilder<VizState>(
              valueListenable: ble.desired,
              builder: (context, desired, ___) {
                return Scaffold(
                  appBar: AppBar(
                    title: const Text('VISUALIZER'),
                    backgroundColor: Retro.panel,
                  ),
                  body: ListView(
                    padding: const EdgeInsets.all(12),
                    children: [
                      CutPanel(
                        cut: 10,
                        child: Row(
                          children: [
                            Container(
                              width: 10,
                              height: 10,
                              color: st == ConnStatus.connected
                                  ? Retro.ok
                                  : (st == ConnStatus.error ? Retro.bad : Retro.yellow),
                            ),
                            const SizedBox(width: 10),
                            Expanded(child: _plate('LINK: ${st.name}', accent: Retro.yellow)),
                            const SizedBox(width: 8),
                            Expanded(child: _plate('MODE: ${desired.mode}', accent: Retro.yellow)),
                            const SizedBox(width: 8),
                            Expanded(child: _plate('FX: ${desired.effect}', accent: Retro.yellow)),
                          ],
                        ),
                      ),

                      if (err != null) ...[
                        const SizedBox(height: 10),
                        CutPanel(cut: 10, child: Text('ERR: $err', style: const TextStyle(color: Colors.redAccent, fontSize: 18))),
                      ],

                      const SizedBox(height: 12),

                      CutPanel(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('CONNECTION', style: TextStyle(color: Retro.yellow, fontSize: 18, letterSpacing: 2)),
                            const SizedBox(height: 10),
                            Row(
                              children: [
                                Expanded(
                                  child: _btn(
                                    (st == ConnStatus.scanning) ? 'SCANNING…' : 'CONNECT',
                                    onPressed: (st == ConnStatus.scanning || st == ConnStatus.connecting)
                                        ? null
                                        : () => ble.scanAndConnect(),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: _btn(
                                    'DISCONNECT',
                                    onPressed: (st == ConnStatus.connected) ? () => ble.disconnect() : null,
                                    fg: Colors.white70,
                                    border: Colors.white24,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),

                      CutPanel(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('MODE', style: TextStyle(color: Retro.yellow, fontSize: 18, letterSpacing: 2)),
                            const SizedBox(height: 10),

                            SegmentedButton<String>(
                              segments: const [
                                ButtonSegment(value: 'mic', label: Text('MIC')),
                                ButtonSegment(value: 'bt', label: Text('BT')),
                              ],
                              selected: {desired.mode},
                              onSelectionChanged: (set) async {
                                final m = set.first;
                                final next = desired.copyWith(mode: m);
                                ble.desired.value = next;

                                if (ble.status.value == ConnStatus.connected) {
                                  await ble.sendPatch({
                                    'mode': m,
                                    'device_addr': next.deviceAddr,
                                    'artist': next.artist,
                                    'title': next.title,
                                    'connected': true,
                                  });
                                }
                              },
                            ),

                            const SizedBox(height: 12),

                            Text('EFFECT', style: TextStyle(color: Retro.yellow, fontSize: 18, letterSpacing: 2)),
                            const SizedBox(height: 10),
                            DropdownButtonFormField<String>(
                              value: desired.effect,
                              items: const [
                                DropdownMenuItem(value: 'bars', child: Text('BARS')),
                                DropdownMenuItem(value: 'vu', child: Text('VU')),
                                DropdownMenuItem(value: 'osc', child: Text('OSC')),
                                DropdownMenuItem(value: 'pulse', child: Text('PULSE')),
                                DropdownMenuItem(value: 'fire', child: Text('FIRE')),
                                DropdownMenuItem(value: 'wave', child: Text('WAVE')),
                              ],
                              onChanged: (v) async {
                                if (v == null) return;
                                final next = desired.copyWith(effect: v);
                                ble.desired.value = next;

                                if (ble.status.value == ConnStatus.connected) {
                                  await ble.sendPatch({'effect': v});
                                }
                              },
                              decoration: const InputDecoration(border: OutlineInputBorder()),
                            ),

                            const SizedBox(height: 12),

                            Text('LEVELS', style: TextStyle(color: Retro.yellow, fontSize: 18, letterSpacing: 2)),
                            const SizedBox(height: 10),

                            _slider('Intensity', desired.intensity, 0, 1, (v) {
                              ble.desired.value = desired.copyWith(intensity: v);
                              _debounced(const Duration(milliseconds: 120), () {
                                if (ble.status.value == ConnStatus.connected) ble.sendPatch({'intensity': v});
                              });
                            }),

                            _slider('Brightness', desired.brightness, 0, 1, (v) {
                              ble.desired.value = desired.copyWith(brightness: v);
                              _debounced(const Duration(milliseconds: 120), () {
                                if (ble.status.value == ConnStatus.connected) ble.sendPatch({'brightness': v});
                              });
                            }),

                            _slider('Gain', desired.gain, 0.1, 6, (v) {
                              ble.desired.value = desired.copyWith(gain: v);
                              _debounced(const Duration(milliseconds: 120), () {
                                if (ble.status.value == ConnStatus.connected) ble.sendPatch({'gain': v});
                              });
                            }),

                            _slider('Smoothing', desired.smoothing, 0, 0.95, (v) {
                              ble.desired.value = desired.copyWith(smoothing: v);
                              _debounced(const Duration(milliseconds: 120), () {
                                if (ble.status.value == ConnStatus.connected) ble.sendPatch({'smoothing': v});
                              });
                            }),
                          ],
                        ),
                      ),
                      CutPanel(
                        child: ValueListenableBuilder<VizState>(
                          valueListenable: ble.remote,
                          builder: (context, remote, _) {
                            final a = remote.artist.isEmpty ? desired.artist : remote.artist;
                            final t = remote.title.isEmpty ? desired.title : remote.title;

                            return Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('NOW PLAYING', style: TextStyle(color: Retro.yellow, fontSize: 18, letterSpacing: 2)),
                                const SizedBox(height: 10),
                                Text('ARTIST: ${a.isEmpty ? "-" : a}', style: const TextStyle(fontSize: 18)),
                                const SizedBox(height: 6),
                                Text('TITLE:  ${t.isEmpty ? "-" : t}', style: const TextStyle(fontSize: 18)),
                              ],
                            );
                          },
                        ),
                      ),
                    ],
                  ),
                );
              },
            );
          },
        );
      },
    );
  }
}

// ===================== Cut Panel + bevel =====================
class CutPanel extends StatelessWidget {
  final Widget child;
  final double cut;
  const CutPanel({super.key, required this.child, this.cut = 12});

  @override
  Widget build(BuildContext context) {
    return ClipPath(
      clipper: CutCornerClipper(cut: cut),
      child: Container(
        decoration: BoxDecoration(
          color: Retro.panel,
          border: Border.all(color: Retro.edge, width: 2),
          boxShadow: const [BoxShadow(blurRadius: 0, offset: Offset(6, 6), color: Colors.black54)],
        ),
        child: Stack(
          children: [
            Positioned.fill(child: IgnorePointer(child: CustomPaint(painter: _BevelPainter()))),
            Padding(padding: const EdgeInsets.all(14), child: child),
          ],
        ),
      ),
    );
  }
}

class CutCornerClipper extends CustomClipper<Path> {
  final double cut;
  CutCornerClipper({this.cut = 10});

  @override
  Path getClip(Size s) {
    final c = cut.clamp(0.0, s.shortestSide / 3);
    return Path()
      ..moveTo(c, 0)
      ..lineTo(s.width - c, 0)
      ..lineTo(s.width, c)
      ..lineTo(s.width, s.height - c)
      ..lineTo(s.width - c, s.height)
      ..lineTo(c, s.height)
      ..lineTo(0, s.height - c)
      ..lineTo(0, c)
      ..close();
  }

  @override
  bool shouldReclip(covariant CutCornerClipper old) => old.cut != cut;
}

class _BevelPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size s) {
    final p1 = Paint()..color = Colors.white.withOpacity(0.06);
    final p2 = Paint()..color = Colors.black.withOpacity(0.35);

    canvas.drawRect(Rect.fromLTWH(0, 0, s.width, 2), p1);
    canvas.drawRect(Rect.fromLTWH(0, 0, 2, s.height), p1);

    canvas.drawRect(Rect.fromLTWH(0, s.height - 2, s.width, 2), p2);
    canvas.drawRect(Rect.fromLTWH(s.width - 2, 0, 2, s.height), p2);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class RectThumbShape extends SliderComponentShape {
  final double w, h;
  const RectThumbShape({this.w = 18, this.h = 14});

  @override
  Size getPreferredSize(bool isEnabled, bool isDiscrete) => Size(w, h);

  @override
  void paint(
    PaintingContext context,
    Offset center, {
    required Animation<double> activationAnimation,
    required Animation<double> enableAnimation,
    required bool isDiscrete,
    required TextPainter labelPainter,
    required RenderBox parentBox,
    required SliderThemeData sliderTheme,
    required TextDirection textDirection,
    required double value,
    required double textScaleFactor,
    required Size sizeWithOverflow,
  }) {
    final canvas = context.canvas;
    final rect = Rect.fromCenter(center: center, width: w, height: h);

    final fill = Paint()..color = sliderTheme.thumbColor ?? Colors.white;
    final stroke = Paint()
      ..color = Colors.black.withOpacity(0.6)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;

    canvas.drawRect(rect, fill);
    canvas.drawRect(rect, stroke);

    final notch = Paint()..color = Colors.black.withOpacity(0.35);
    canvas.drawRect(Rect.fromCenter(center: center, width: 2, height: h - 4), notch);
  }
}
