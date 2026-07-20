import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:uuid/uuid.dart';
import 'package:webview_flutter/webview_flutter.dart';

const websiteUrl = 'https://kyawmintun08.github.io/Japan-Auction-Car-Checker/?jacc_app=1';
const appConfigUrl = 'https://kyawmintun08.github.io/Japan-Auction-Car-Checker/app-config.json';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const JaccApp());
}

class JaccApp extends StatelessWidget {
  const JaccApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'JACC',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          brightness: Brightness.dark,
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFFC8102E),
            brightness: Brightness.dark,
          ),
          scaffoldBackgroundColor: const Color(0xFF050B16),
        ),
        home: const JaccWebView(),
      );
}

class JaccWebView extends StatefulWidget {
  const JaccWebView({super.key});

  @override
  State<JaccWebView> createState() => _JaccWebViewState();
}

class _JaccWebViewState extends State<JaccWebView> {
  static const _storage = FlutterSecureStorage();
  late final WebViewController _controller;
  StreamSubscription<List<ConnectivityResult>>? _networkSub;
  String _deviceId = '';
  bool _loading = true;
  bool _offline = false;
  bool _showSplash = true;
  int _progress = 0;
  DateTime? _lastBackPressed;

  @override
  void initState() {
    super.initState();
    _prepare();
  }

  Future<void> _prepare() async {
    _deviceId = await _storage.read(key: 'jacc_installation_id') ?? const Uuid().v4();
    await _storage.write(key: 'jacc_installation_id', value: _deviceId);
    _setupWebView();
    _networkSub = Connectivity().onConnectivityChanged.listen((results) {
      final offline = results.every((r) => r == ConnectivityResult.none);
      if (!mounted) return;
      final reconnecting = _offline && !offline;
      setState(() => _offline = offline);
      if (reconnecting) _controller.reload();
    });
    if (mounted) setState(() {});
    unawaited(_checkForUpdate());
  }

  void _setupWebView() {
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFFF4F1EC))
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (value) => mounted ? setState(() => _progress = value) : null,
          onPageStarted: (_) => mounted ? setState(() => _loading = true) : null,
          onPageFinished: (_) async {
            if (mounted) {
              setState(() {
                _loading = false;
                _offline = false;
                _showSplash = false;
              });
            }
            await _installDeviceBridge();
          },
          onWebResourceError: (error) {
            if (error.isForMainFrame == true && mounted) {
              setState(() {
                _offline = true;
                _showSplash = false;
              });
            }
          },
          onNavigationRequest: (request) async {
            final uri = Uri.tryParse(request.url);
            if (uri == null) return NavigationDecision.prevent;
            const external = {'tel', 'mailto', 'sms', 'tg', 'whatsapp', 'market', 'intent'};
            if (external.contains(uri.scheme)) {
              await launchUrl(uri, mode: LaunchMode.externalApplication);
              return NavigationDecision.prevent;
            }
            final host = uri.host.toLowerCase();
            final allowed = host == 'kyawmintun08.github.io' ||
                host == 'script.google.com' ||
                host == 'script.googleusercontent.com' ||
                host == 'docs.google.com';
            if ((uri.scheme == 'http' || uri.scheme == 'https') && !allowed) {
              await launchUrl(uri, mode: LaunchMode.externalApplication);
              return NavigationDecision.prevent;
            }
            return NavigationDecision.navigate;
          },
        ),
      )
      ..loadRequest(Uri.parse(websiteUrl));
  }

  Future<void> _installDeviceBridge() async {
    final escaped = _deviceId.replaceAll(r'\', r'\\').replaceAll("'", r"\'");
    await _controller.runJavaScript('''
      (() => {
        const deviceId = '$escaped';
        localStorage.setItem('jacc_installation_id', deviceId);

        const sessionKey = 'jan_session';
        const savedSession = localStorage.getItem(sessionKey);
        if (savedSession && !sessionStorage.getItem(sessionKey)) {
          sessionStorage.setItem(sessionKey, savedSession);
          location.reload();
          return;
        }
        if (!window.__jaccPersistentSessionInstalled) {
          window.__jaccPersistentSessionInstalled = true;
          const originalSetItem = sessionStorage.setItem.bind(sessionStorage);
          const originalRemoveItem = sessionStorage.removeItem.bind(sessionStorage);
          sessionStorage.setItem = (key, value) => {
            originalSetItem(key, value);
            if (key === sessionKey) localStorage.setItem(key, value);
          };
          sessionStorage.removeItem = (key) => {
            originalRemoveItem(key);
            if (key === sessionKey) localStorage.removeItem(key);
          };
        }

        if (window.__jaccNativeFetchInstalled) return;
        window.__jaccNativeFetchInstalled = true;
        const originalFetch = window.fetch.bind(window);
        window.fetch = async (input, init = {}) => {
          try {
            if (init && typeof init.body === 'string') {
              const body = JSON.parse(init.body);
              if (body && (body.action === 'verifyLogin' || body.action === 'verifyToken')) {
                body.deviceId = deviceId;
                body.app = 'flutter';
                init = {...init, body: JSON.stringify(body)};
              }
            }
          } catch (_) {}
          return originalFetch(input, init);
        };
      })();
    ''');
  }

  Future<void> _checkForUpdate() async {
    try {
      final response = await http
          .get(Uri.parse('$appConfigUrl?t=${DateTime.now().millisecondsSinceEpoch}'))
          .timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) return;
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final info = await PackageInfo.fromPlatform();
      final latest = (data['latestVersion'] ?? '').toString();
      if (latest.isEmpty || !_isNewerVersion(latest, info.version)) return;
      if (!mounted) return;
      final force = data['forceUpdate'] == true;
      final url = (data['apkUrl'] ?? '').toString();
      final message = (data['updateMessage'] ?? 'JACC version အသစ်ရရှိနိုင်ပါပြီ။').toString();
      await showDialog<void>(
        context: context,
        barrierDismissible: !force,
        builder: (context) => PopScope(
          canPop: !force,
          child: AlertDialog(
            title: Text('JACC $latest Update'),
            content: Text(message),
            actions: [
              if (!force)
                TextButton(onPressed: () => Navigator.pop(context), child: const Text('နောက်မှ')),
              FilledButton(
                onPressed: url.isEmpty
                    ? null
                    : () async {
                        await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
                        if (!force && context.mounted) Navigator.pop(context);
                      },
                child: const Text('Update Now'),
              ),
            ],
          ),
        ),
      );
    } catch (_) {}
  }

  bool _isNewerVersion(String latest, String current) {
    List<int> parts(String value) => value
        .split('.')
        .map((e) => int.tryParse(e.replaceAll(RegExp(r'[^0-9]'), '')) ?? 0)
        .toList();
    final a = parts(latest);
    final b = parts(current);
    final length = a.length > b.length ? a.length : b.length;
    for (var i = 0; i < length; i++) {
      final av = i < a.length ? a[i] : 0;
      final bv = i < b.length ? b[i] : 0;
      if (av != bv) return av > bv;
    }
    return false;
  }

  Future<void> _back() async {
    if (await _controller.canGoBack()) {
      await _controller.goBack();
      return;
    }
    final now = DateTime.now();
    if (_lastBackPressed == null ||
        now.difference(_lastBackPressed!) > const Duration(seconds: 2)) {
      _lastBackPressed = now;
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('App ပိတ်ရန် Back ကို နောက်တစ်ကြိမ်နှိပ်ပါ')),
        );
      }
      return;
    }
    if (Platform.isAndroid) SystemNavigator.pop();
  }

  @override
  void dispose() {
    _networkSub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_deviceId.isEmpty) return const JaccSplash();
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (_, __) => _back(),
      child: Scaffold(
        body: SafeArea(
          child: Stack(
            children: [
              WebViewWidget(controller: _controller),
              if (_loading && !_showSplash)
                LinearProgressIndicator(value: _progress == 0 ? null : _progress / 100),
              if (_showSplash) const JaccSplash(),
              if (_offline)
                ColoredBox(
                  color: const Color(0xFF050B16),
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.wifi_off_rounded, size: 64, color: Colors.white70),
                        const SizedBox(height: 14),
                        const Text(
                          'No Internet Connection',
                          style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 8),
                        const Text(
                          'အင်တာနက်ပြန်ချိတ်ပြီး ထပ်စမ်းပါ',
                          style: TextStyle(color: Colors.white60),
                        ),
                        const SizedBox(height: 18),
                        FilledButton.icon(
                          onPressed: () {
                            setState(() => _offline = false);
                            _controller.reload();
                          },
                          icon: const Icon(Icons.refresh),
                          label: const Text('Retry'),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class JaccSplash extends StatelessWidget {
  const JaccSplash({super.key});

  @override
  Widget build(BuildContext context) => const ColoredBox(
        color: Color(0xFF050B16),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.directions_car_filled_rounded,
                size: 72,
                color: Color(0xFFC8102E),
              ),
              SizedBox(height: 14),
              Text(
                'JACC',
                style: TextStyle(
                  fontSize: 52,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 7,
                  color: Colors.white,
                ),
              ),
              SizedBox(height: 8),
              Text(
                'JAPAN AUCTION CAR CHECKER',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 2.2,
                  color: Color(0xFFAAB3C2),
                ),
              ),
              SizedBox(height: 34),
              SizedBox(
                width: 28,
                height: 28,
                child: CircularProgressIndicator(
                  strokeWidth: 3,
                  color: Color(0xFFC8102E),
                ),
              ),
              SizedBox(height: 14),
              Text(
                'Loading...',
                style: TextStyle(fontSize: 12, color: Color(0xFF7E8796)),
              ),
            ],
          ),
        ),
      );
}
