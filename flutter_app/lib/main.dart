import 'dart:async';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:uuid/uuid.dart';
import 'package:webview_flutter/webview_flutter.dart';

const websiteUrl = 'https://kyawmintun08.github.io/Japan-Auction-Car-Checker/?jacc_app=1';

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
          colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFC8102E)),
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
  int _progress = 0;

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
            if (mounted) setState(() { _loading = false; _offline = false; });
            await _installDeviceBridge();
          },
          onWebResourceError: (error) {
            if (error.isForMainFrame == true && mounted) setState(() => _offline = true);
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

  Future<void> _back() async {
    if (await _controller.canGoBack()) {
      await _controller.goBack();
    } else if (Platform.isAndroid) {
      SystemNavigator.pop();
    }
  }

  @override
  void dispose() {
    _networkSub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_deviceId.isEmpty) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (_, __) => _back(),
      child: Scaffold(
        body: SafeArea(
          child: Stack(
            children: [
              WebViewWidget(controller: _controller),
              if (_loading) LinearProgressIndicator(value: _progress == 0 ? null : _progress / 100),
              if (_offline)
                ColoredBox(
                  color: const Color(0xFFF4F1EC),
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.wifi_off_rounded, size: 64),
                        const SizedBox(height: 14),
                        const Text('Internet Connection မရှိပါ', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                        const SizedBox(height: 18),
                        FilledButton.icon(
                          onPressed: () { setState(() => _offline = false); _controller.reload(); },
                          icon: const Icon(Icons.refresh),
                          label: const Text('ပြန်ကြိုးစားမယ်'),
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
