/// Scansione sottorete per trovare la lavatrice Candy.
///
/// Ricava l'IP locale del dispositivo, deriva la sottorete /24 e scansiona
/// in parallelo tutti i 254 host cercando il server HTTP cifrato della Candy.
library;

import 'dart:io';

import 'package:dio/dio.dart';

/// Ricava l'IPv4 locale del dispositivo.
///
/// Esclude loopback e link-local. Ritorna il primo IPv4 valido trovato,
/// o lancia [SocketException] se non c'è alcuna interfaccia di rete attiva.
Future<String> getLocalIp() async {
  final interfaces = await NetworkInterface.list(
      type: InternetAddressType.IPv4, includeLoopback: false, includeLinkLocal: false);
  for (final iface in interfaces) {
    for (final addr in iface.addresses) {
      if (addr.type == InternetAddressType.IPv4 && !addr.isLoopback) {
        return addr.address;
      }
    }
  }
  throw SocketException('Nessuna interfaccia di rete IPv4 disponibile.');
}

/// Ritorna i primi 3 ottetti dell'IP (es. "192.168.1.42" -> "192.168.1").
String subnetPrefix(String localIp) {
  final parts = localIp.split('.');
  if (parts.length < 3) {
    throw FormatException('IP non valido: $localIp');
  }
  return parts.sublist(0, 3).join('.');
}

/// Verifica che il body sembri una risposta cifrata Candy:
/// stringa esadecimale lunga (>50 char), tipica dell'XOR della lavatrice.
bool _looksLikeCandyResponse(String body) {
  if (body.length < 50) return false;
  return RegExp(r'^[0-9a-fA-F]+$').hasMatch(body);
}

/// Scansiona la sottorete /24 alla ricerca della lavatrice Candy.
///
/// Prova in parallelo gli host da `<subnet>.1` a `<subnet>.254` verso
/// `http://<ip>/http-read.json?encrypted=1`. Il primo host che risponde
/// 200 con body esadecimale lungo viene considerato la lavatrice.
///
/// [concurrency] numero di richieste parallele (default 50).
/// [timeout] timeout di connect+receive per ogni tentativo.
/// [onProgress] callback `(scanned, total)` dopo ogni tentativo.
///
/// Ritorna l'IP trovato, oppure `null` se nessun host risponde.
/// [cancelFlag] se fornito, la scansione si interrompe quando diventa `true`.
Future<String?> scanForCandy({
  required String subnet,
  int concurrency = 50,
  Duration timeout = const Duration(milliseconds: 1500),
  void Function(int scanned, int total)? onProgress,
  bool Function()? cancelFlag,
}) async {
  final hosts = [for (var i = 1; i <= 254; i++) '$subnet.$i'];
  final total = hosts.length;
  final dio = Dio(BaseOptions(
    connectTimeout: timeout,
    receiveTimeout: timeout,
    sendTimeout: timeout,
    responseType: ResponseType.plain,
    validateStatus: (s) => s != null && s < 500,
  ));

  var scanned = 0;
  String? found;
  final pool = <Future<void>>[];

  for (final ip in hosts) {
    // interruzione
    if (cancelFlag != null && cancelFlag()) break;
    if (found != null) break;

    pool.add(() async {
      if (found != null) return;
      try {
        final resp = await dio.get<dynamic>(
          'http://$ip/http-read.json?encrypted=1',
        );
        if (resp.statusCode == 200) {
          final body = resp.data?.toString() ?? '';
          if (_looksLikeCandyResponse(body)) {
            found = ip;
          }
        }
      } catch (_) {
        // host spento/non Candy: ignora
      } finally {
        scanned++;
        onProgress?.call(scanned, total);
      }
    }());

    // throttle: aspetta che almeno uno slot si liberi
    if (pool.length >= concurrency) {
      await Future.any(pool);
      pool.removeWhere((f) => _isCompleted(f));
    }
  }

  // attende tutti i tentativi in corso (per il progress counter)
  await Future.wait(pool);
  return found;
}

/// Verifica (best-effort) se un Future è completato senza attendere.
bool _isCompleted(Future<void> f) {
  var done = false;
  f.whenComplete(() => done = true);
  return done;
}
