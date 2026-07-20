import 'dart:async';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:uuid/uuid.dart';
import 'package:webview_flutter/webview_flutter.dart';

const String jaccWebsiteUrl =
    'https://kyawmintun08.github.io/Japan-Auction-Car-Checker/?jacc_app=1';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Color(0xFFC8102E),
      statusBarIconBrightness: Brightness.light,
      systemNavigationBarColor: Colors.white,
      systemNavigationBarIconBrightness: Brightness.dark,
    ),
  );
  runApp(const JaccApp());
}

class JaccApp extends StatelessWidget {
  const JaccApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'JACC',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFC8102E)),
      ),
      home: const JaccWebViewScreen(),
    );
  }
}

class JaccWebViewScreen extends StatefulWidget {
  const JaccWebViewScreen({super.key});

  @override
  State<JaccWebViewScreen> createState() => _JaccWebViewScreenState();
}

class _JaccWebViewScreenState extends State<JaccWebViewScreen> {
  static const FlutterSecureStorage _storage = FlutterSecureStorage();
  late final WebViewController _controller;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;

  bool _loading = true;
  bool _offline = false;
  int _progress = 0;
  String? _deviceId;

  @override
  void initState() {
    super.initState();
    _setupDeviceIdentity();
    _setupWebView();
    _watchConnectivity();
  }

  Future<void> _setupDeviceIdentity() async {
    var id = await _storage.read(key: 'jacc_installation_id');
    id ??= const Uuid().v4();
    await _storage.write(key: 'jacc_installation_id', value: id);
    if (mounted) setState(() => _deviceId = id);
  }

  void _setupWebView() {
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFFF4F1EC))
      ..addJavaScriptChannel(
        'JACCNative',
        onMessageReceived: (message) async {
          if (message.message == 'reload') await _controller.reload();
        },
      )
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (progress) {
            if (mounted) setState(() => _progress = progress);
          },
          onPageStarted: (_) {
            if (mounted) setState(() => _loading = true);
          },
          onPageFinished: (_) async {
            if (mounted) {
              setState(() {
                _loading = false;
                _offline = false;
              });
            }
            final id = _deviceId;
            if (id != null) {
              await _controller.runJavaScript(
                "localStorage.setItem('jacc_installation_id', ${_jsString(id)});",
              );
            }
          },
          onWebResourceError: (error) {
            if (error.isForMainFrame == true && mounted) {
              setState(() => _offline = true);
            }
          },
          onNavigationRequest: (request) async {
            final uri = Uri.tryParse(request.url);
            if (uri == null) return NavigationDecision.prevent;

            const externalSchemes = {
              'tel',
              'mailto',
              'sms',
              'tg',
              'whatsapp',
              'market',
              'intent',
            };
            if (externalSchemes.contains(uri.scheme)) {
              await _launchExternal(uri);
              return NavigationDecision.prevent;
            }

            final host = uri.host.toLowerCase();
            final isJaccHost = host == 'kyawmintun08.github.io' ||
                host == 'script.google.com' ||
                host == 'script.googleusercontent.com' ||
                host == 'docs.google.com';
            if ((uri.scheme == 'http' || uri.scheme == 'https') && !isJaccHost) {
              await _launchExternal(uri);
              return NavigationDecision.prevent;
            }
            return NavigationDecision.navigate;
          },
        ),
      )
      ..loadRequest(Uri.parse(jaccWebsiteUrl));
  }

  String _jsString(String value) =>
      "'${value.replaceAll(r'\\', r'\\\\').replaceAll("'", r"\'")}'";

  Future<void> _launchExternal(Uri uri) async {
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('ဒီ Link ကို ဖွင့်လို့မရပါ။')),
      );
    }
  }

  void _watchConnectivity() {
    _connectivitySubscription =
        Connectivity().onConnectivityChanged.listen((results) {
      final offline = results.every((item) => item == ConnectivityResult.none);
      if (!mounted) return;
      final wasOffline = _offline;
      setState(() => _offline = offline);
      if (wasOffline && !offline) _controller.reload();
    });
  }

  Future<void> _handleBack() async {
    if (await _controller.canGoBack()) {
      await _controller.goBack();
      return;
    }

    if (!mounted) return;
    final shouldExit = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('JACC App ပိတ်မလား?'),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('မပိတ်သေးပါ'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('ပိတ်မယ်'),
              ),
            ],
          ),
        ) ??
        false;

    if (shouldExit && Platform.isAndroid) SystemNavigator.pop();
  }

  @override
  void dispose() {
    _connectivitySubscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (_, __) => _handleBack(),
      child: Scaffold(
        body: SafeArea(
          child: Stack(
            children: [
              WebViewWidget(controller: _controller),
              if (_loading)
                LinearProgressIndicator(
                  value: _progress == 0 ? null : _progress / 100,
                ),
              if (_offline)
                ColoredBox(
                  color: const Color(0xFFF4F1EC),
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.all(28),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.wifi_off_rounded, size: 64),
                          const SizedBox(height: 16),
                          const Text(
                            'Internet Connection မရှိပါ',
                            style: TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 8),
                          const Text(
                            'လိုင်းပြန်ကောင်းလာရင် JACC ကို ပြန်ဖွင့်နိုင်ပါတယ်။',
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 20),
                          FilledButton.icon(
                            onPressed: () async {
                              setState(() => _offline = false);
                              await _controller.reload();
                            },
                            icon: const Icon(Icons.refresh),
                            label: const Text('ပြန်ကြိုးစားမယ်'),
                          ),
                        ],
                      ),
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
