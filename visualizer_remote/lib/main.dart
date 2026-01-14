import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:permission_handler/permission_handler.dart';

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
      title: 'Visualizer',
      theme: base.copyWith(
        textTheme: GoogleFonts.vt323TextTheme(base.textTheme).apply(
          bodyColor: Colors.white,
          displayColor: Colors.white,
        ),
      ),
      home: const PermissionGate(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class Retro {
  static const bg = Color(0xFF101114);
  static const panel = Color(0xFF1B1D22);
  static const edge = Color(0xFF30333B);
  static const yellow = Color(0xFFFFD166);
  static const ok = Color(0xFF4AF2A1);
  static const bad = Color(0xFFFF4D6D);
}

// ===================== BLE GATT UUIDs (ustal i trzymaj stałe) =====================
const String kSvc = '12345678-1234-5678-1234-56789abcdef0';
const String kMode = '12345678-1234-5678-1234-56789abcdef1';
const String kEffect = '12345678-1234-5678-1234-56789abcdef2';
const String kBrightness = '12345678-1234-5678-1234-56789abcdef3';
const String kIntensity = '12345678-1234-5678-1234-56789abcdef4';
const String kGain = '12345678-1234-5678-1234-56789abcdef5';
const String kSmoothing = '12345678-1234-5678-1234-56789abcdef6';
const String kPassthrough = '12345678-1234-5678-1234-56789abcdef7';
const String kStateNotify = '12345678-1234-5678-1234-56789abcdef8';

// Device advertising name (ustal w Pi BLE server)
const String kDeviceName = 'Visualizer';

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

    final granted = results.values.any((r) => r.isGranted);
    setState(() => _ok = granted);
  }

  Widget _panel({required Widget child, double cut = 14}) {
    return CutPanel(cut: cut, child: child);
  }

  @override
  Widget build(BuildContext context) {
    if (_ok) return const RootBle();

    return Scaffold(
      backgroundColor: Retro.bg,
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: _panel(
            cut: 16,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.bluetooth, size: 64, color: Retro.yellow),
                const SizedBox(height: 12),
                const Text('BLUETOOTH REQUIRED', style: TextStyle(fontSize: 26, letterSpacing: 2)),
                const SizedBox(height: 10),
                const Text(
                  'Connect to your Visualizer and control effects.\n\n'
                  'If you deny permission, the app cannot work.',
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

// ===================== BLE State =====================

class BleState {
  final String mode;
  final String effect;
  final double brightness;
  final double intensity;
  final double gain;
  final double smoothing;
  final bool passthrough;
  final Map<String, dynamic> nowPlaying;

  const BleState({
    required this.mode,
    required this.effect,
    required this.brightness,
    required this.intensity,
    required this.gain,
    required this.smoothing,
    required this.passthrough,
    required this.nowPlaying,
  });

  factory BleState.empty() => const BleState(
        mode: 'mic',
        effect: 'bars',
        brightness: 0.55,
        intensity: 0.75,
        gain: 1.0,
        smoothing: 0.65,
        passthrough: true,
        nowPlaying: {},
      );

  factory BleState.fromJson(Map<String, dynamic> j) {
    final np = (j['nowplaying'] is Map) ? Map<String, dynamic>.from(j['nowplaying']) : <String, dynamic>{};
    return BleState(
      mode: (j['mode'] ?? 'mic').toString(),
      effect: (j['effect'] ?? 'bars').toString(),
      brightness: _d(j['brightness'], 0.55),
      intensity: _d(j['intensity'], 0.75),
      gain: _d(j['gain'], 1.0),
      smoothing: _d(j['smoothing'], 0.65),
      passthrough: (j['passthrough'] ?? true) == true,
      nowPlaying: np,
    );
  }

  static double _d(dynamic v, double fb) {
    if (v == null) return fb;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? fb;
  }
}

// ===================== BLE Controller =====================

class BleController {
  BluetoothDevice? device;

  BluetoothCharacteristic? chMode;
  BluetoothCharacteristic? chEffect;
  BluetoothCharacteristic? chBrightness;
  BluetoothCharacteristic? chIntensity;
  BluetoothCharacteristic? chGain;
  BluetoothCharacteristic? chSmoothing;
  BluetoothCharacteristic? chPassthrough;
  BluetoothCharacteristic? chNotify;

  StreamSubscription? _scanSub;
  StreamSubscription? _connSub;
  StreamSubscription? _notifySub;

  final ValueNotifier<bool> connected = ValueNotifier(false);
  final ValueNotifier<String?> error = ValueNotifier(null);
  final ValueNotifier<BleState> state = ValueNotifier(BleState.empty());

  Future<void> startScanAndConnect({Duration timeout = const Duration(seconds: 6)}) async {
    error.value = null;

    try {
      await FlutterBluePlus.stopScan();
    } catch (_) {}

    await FlutterBluePlus.startScan(timeout: timeout);

    _scanSub?.cancel();
    _scanSub = FlutterBluePlus.scanResults.listen((results) async {
      for (final r in results) {
        final name = r.device.platformName;
        if (name == kDeviceName) {
          await FlutterBluePlus.stopScan();
          await _connect(r.device);
          return;
        }
      }
    });
  }

  Future<void> _connect(BluetoothDevice d) async {
    device = d;
    error.value = null;

    try {
      await d.connect(autoConnect: true, timeout: const Duration(seconds: 8));
    } catch (_) {}

    _connSub?.cancel();
    _connSub = d.connectionState.listen((s) {
      connected.value = (s == BluetoothConnectionState.connected);
      if (!connected.value) error.value ??= 'Disconnected';
    });

    await _discoverChars(d);
    await _enableNotify();
    connected.value = true;
  }

  Future<void> _discoverChars(BluetoothDevice d) async {
    final services = await d.discoverServices();
    final svc = services.where((s) => s.uuid.toString().toLowerCase() == kSvc).toList();
    if (svc.isEmpty) throw Exception('GATT service not found');
    final s = svc.first;

    BluetoothCharacteristic? pick(String uuid) {
      return s.characteristics.where((c) => c.uuid.toString().toLowerCase() == uuid).firstOrNull;
    }

    chMode = pick(kMode);
    chEffect = pick(kEffect);
    chBrightness = pick(kBrightness);
    chIntensity = pick(kIntensity);
    chGain = pick(kGain);
    chSmoothing = pick(kSmoothing);
    chPassthrough = pick(kPassthrough);
    chNotify = pick(kStateNotify);

    if (chNotify == null) throw Exception('Notify characteristic missing');
  }

  Future<void> _enableNotify() async {
    final ch = chNotify!;
    await ch.setNotifyValue(true);

    _notifySub?.cancel();
    _notifySub = ch.lastValueStream.listen((bytes) {
      try {
        final text = utf8.decode(bytes);
        final j = jsonDecode(text);
        if (j is Map<String, dynamic>) {
          state.value = BleState.fromJson(j);
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

    if (device != null) {
      try {
        await device!.disconnect();
      } catch (_) {}
    }
    connected.value = false;
  }

  Future<void> writeString(BluetoothCharacteristic? ch, String v) async {
    if (ch == null) return;
    await ch.write(utf8.encode(v), withoutResponse: true);
  }

  Future<void> setMode(String v) => writeString(chMode, v);
  Future<void> setEffect(String v) => writeString(chEffect, v);
  Future<void> setBrightness(double v) => writeString(chBrightness, v.toStringAsFixed(3));
  Future<void> setIntensity(double v) => writeString(chIntensity, v.toStringAsFixed(3));
  Future<void> setGain(double v) => writeString(chGain, v.toStringAsFixed(3));
  Future<void> setSmoothing(double v) => writeString(chSmoothing, v.toStringAsFixed(3));
  Future<void> setPassthrough(bool v) => writeString(chPassthrough, v ? '1' : '0');
}

extension _FirstOrNull<E> on Iterable<E> {
  E? get firstOrNull => isEmpty ? null : first;
}

// ===================== Root UI (no rounded borders) =====================

class RootBle extends StatefulWidget {
  const RootBle({super.key});
  @override
  State<RootBle> createState() => _RootBleState();
}

class _RootBleState extends State<RootBle> {
  final BleController ble = BleController();
  int _tab = 0;
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    ble.startScanAndConnect();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    ble.disconnect();
    super.dispose();
  }

  void _setDebounced(VoidCallback f) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 120), f);
  }

  Widget _panel({required Widget child, double cut = 12}) => CutPanel(cut: cut, child: child);

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

  Widget _topOsd(BleState s, bool connected) {
    final c = connected ? Retro.ok : Retro.bad;
    final label = connected ? 'OK' : 'NO LINK';

    return CutPanel(
      cut: 10,
      child: Row(
        children: [
          Container(width: 10, height: 10, decoration: BoxDecoration(color: c, shape: BoxShape.rectangle)),
          const SizedBox(width: 10),
          const Text('VISUALIZER', style: TextStyle(fontSize: 20, letterSpacing: 2)),
          const Spacer(),
          _plate('LINK: $label', accent: c),
          const SizedBox(width: 8),
          _plate('MODE: ${s.mode}', accent: Retro.yellow),
          const SizedBox(width: 8),
          _plate('FX: ${s.effect}', accent: Retro.yellow),
        ],
      ),
    );
  }

  Widget _home(BleState s, bool connected, String? err) {
    final np = s.nowPlaying;
    final source = (np['source'] ?? s.mode).toString();
    final title = (np['title'] ?? '').toString().trim();
    final artist = (np['artist'] ?? '').toString().trim();
    final album = (np['album'] ?? '').toString().trim();

    final line = (artist.isNotEmpty && title.isNotEmpty) ? '$artist — $title' : (title.isNotEmpty ? title : artist);

    return Column(
      children: [
        _topOsd(s, connected),
        const SizedBox(height: 12),
        _panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('NOW PLAYING', style: TextStyle(color: Retro.yellow, fontSize: 18, letterSpacing: 2)),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _plate('SRC: $source', accent: Retro.yellow),
                  if (connected) _plate('CONNECTED', accent: Retro.ok) else _plate('DISCONNECTED', accent: Retro.bad),
                ],
              ),
              const SizedBox(height: 10),
              Text(line.isNotEmpty ? line : '—', style: const TextStyle(fontSize: 22)),
              if (album.isNotEmpty) Text(album, style: const TextStyle(color: Colors.white60, fontSize: 18)),
              if (err != null) ...[
                const SizedBox(height: 8),
                Text('ERR: $err', style: const TextStyle(color: Colors.redAccent, fontSize: 16)),
              ],
            ],
          ),
        ),
        const SizedBox(height: 12),
        _panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('QUICK', style: TextStyle(color: Retro.yellow, fontSize: 18, letterSpacing: 2)),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: SizedBox(
                      height: 46,
                      child: ElevatedButton(
                        onPressed: () => ble.startScanAndConnect(),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.black.withOpacity(0.25),
                          foregroundColor: Retro.yellow,
                          shape: const BeveledRectangleBorder(),
                          side: BorderSide(color: Retro.yellow.withOpacity(0.65), width: 2),
                        ),
                        child: const Text('FIND', style: TextStyle(letterSpacing: 2, fontSize: 18)),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: SizedBox(
                      height: 46,
                      child: ElevatedButton(
                        onPressed: () => ble.disconnect(),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.black.withOpacity(0.25),
                          foregroundColor: Colors.white70,
                          shape: const BeveledRectangleBorder(),
                          side: BorderSide(color: Colors.white24, width: 2),
                        ),
                        child: const Text('DISCONNECT', style: TextStyle(letterSpacing: 2, fontSize: 18)),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _controls(BleState s) {
    return Column(
      children: [
        _panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('MODE', style: TextStyle(color: Retro.yellow, fontSize: 18, letterSpacing: 2)),
              const SizedBox(height: 10),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'mic', label: Text('MIC')),
                  ButtonSegment(value: 'bluetooth', label: Text('BT')),
                  ButtonSegment(value: 'local', label: Text('LOCAL')),
                ],
                selected: {s.mode},
                onSelectionChanged: (set) async => ble.setMode(set.first),
              ),
              const SizedBox(height: 10),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Mic passthrough'),
                subtitle: const Text('mic → speaker (only MIC mode)'),
                value: s.passthrough,
                onChanged: (v) async => ble.setPassthrough(v),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        _panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('EFFECT', style: TextStyle(color: Retro.yellow, fontSize: 18, letterSpacing: 2)),
              const SizedBox(height: 10),
              DropdownButtonFormField<String>(
                value: s.effect,
                items: const [
                  DropdownMenuItem(value: 'bars', child: Text('BARS')),
                  DropdownMenuItem(value: 'vu', child: Text('VU')),
                  DropdownMenuItem(value: 'scope', child: Text('SCOPE')),
                  DropdownMenuItem(value: 'radial', child: Text('RADIAL')),
                  DropdownMenuItem(value: 'fire', child: Text('FIRE')),
                  DropdownMenuItem(value: 'wave', child: Text('WAVE')),
                ],
                onChanged: (v) async {
                  if (v == null) return;
                  await ble.setEffect(v);
                },
                decoration: const InputDecoration(border: OutlineInputBorder()),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        _panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('LEVELS', style: TextStyle(color: Retro.yellow, fontSize: 18, letterSpacing: 2)),
              const SizedBox(height: 10),
              _slider('Intensity', s.intensity, 0, 1, (v) => _setDebounced(() => ble.setIntensity(v))),
              _slider('Brightness', s.brightness, 0, 1, (v) => _setDebounced(() => ble.setBrightness(v))),
              _slider('Gain', s.gain, 0.1, 6, (v) => _setDebounced(() => ble.setGain(v))),
              _slider('Smoothing', s.smoothing, 0, 0.95, (v) => _setDebounced(() => ble.setSmoothing(v))),
            ],
          ),
        ),
      ],
    );
  }

  Widget _device(bool connected, String? err) {
    return Column(
      children: [
        _panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('DEVICE', style: TextStyle(color: Retro.yellow, fontSize: 18, letterSpacing: 2)),
              const SizedBox(height: 10),
              Text(
                connected ? 'Connected to $kDeviceName.' : 'Searching for $kDeviceName…',
                style: const TextStyle(color: Colors.white70, fontSize: 18),
              ),
              if (err != null) ...[
                const SizedBox(height: 8),
                Text('ERR: $err', style: const TextStyle(color: Colors.redAccent, fontSize: 16)),
              ],
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: SizedBox(
                      height: 46,
                      child: ElevatedButton(
                        onPressed: () => ble.startScanAndConnect(),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.black.withOpacity(0.25),
                          foregroundColor: Retro.yellow,
                          shape: const BeveledRectangleBorder(),
                          side: BorderSide(color: Retro.yellow.withOpacity(0.65), width: 2),
                        ),
                        child: const Text('FIND', style: TextStyle(letterSpacing: 2, fontSize: 18)),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: SizedBox(
                      height: 46,
                      child: ElevatedButton(
                        onPressed: () => ble.disconnect(),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.black.withOpacity(0.25),
                          foregroundColor: Colors.white70,
                          shape: const BeveledRectangleBorder(),
                          side: BorderSide(color: Colors.white24, width: 2),
                        ),
                        child: const Text('DISCONNECT', style: TextStyle(letterSpacing: 2, fontSize: 18)),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: ble.connected,
      builder: (context, connected, _) {
        return ValueListenableBuilder<String?>(
          valueListenable: ble.error,
          builder: (context, err, __) {
            return ValueListenableBuilder<BleState>(
              valueListenable: ble.state,
              builder: (context, s, ___) {
                final pages = <Widget>[
                  _home(s, connected, err),
                  _controls(s),
                  _device(connected, err),
                ];

                return Scaffold(
                  backgroundColor: Retro.bg,
                  appBar: AppBar(
                    title: const Text('VISUALIZER'),
                    backgroundColor: Retro.panel,
                  ),
                  body: ListView(
                    padding: const EdgeInsets.all(12),
                    children: [pages[_tab]],
                  ),
                  bottomNavigationBar: NavigationBar(
                    selectedIndex: _tab,
                    onDestinationSelected: (i) => setState(() => _tab = i),
                    destinations: const [
                      NavigationDestination(icon: Icon(Icons.home), label: 'Home'),
                      NavigationDestination(icon: Icon(Icons.tune), label: 'Controls'),
                      NavigationDestination(icon: Icon(Icons.memory), label: 'Device'),
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

// ===================== Cut Panel + bevel (no rounded borders) =====================

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
          boxShadow: const [
            BoxShadow(blurRadius: 0, offset: Offset(6, 6), color: Colors.black54),
          ],
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

// ===================== Rectangular thumb (kills Material look) =====================

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
