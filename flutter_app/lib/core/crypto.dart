/// Crittografia XOR e derivazione chiave per la lavatrice Candy.
///
/// Porting fedele di candy_sendprogram.py (getkey + xor_encode/decode).
/// La chiave è di 16 byte ASCII, fissa per dispositivo.
library;

import 'dart:convert';
import 'package:dio/dio.dart';

/// Stringa nota usata per ricavare la chiave via endpoint BM=1.
const String kKnownResponse = '{"response":"SUCCESS"}';

/// Prefisso noto della risposta di stato (per fallback known-plaintext).
/// Corrisponde a: {\r\n\t"statusLavatrice":{\r\n\t\t"WiFiStatus":"
const String kKnownStatusPrefix =
    '{\r\n\t"statusLavatrice":{\r\n\t\t"WiFiStatus":"';

/// Lunghezza attesa della chiave.
const int kKeyLength = 16;

/// Cifra un plaintext in una stringa esadecimale (per il parametro data=).
String xorEncode(String plaintext, String key) {
  final out = StringBuffer();
  for (int i = 0; i < plaintext.length; i++) {
    final int xored = plaintext.codeUnitAt(i) ^ key.codeUnitAt(i % key.length);
    out.write(xored.toRadixString(16).padLeft(2, '0'));
  }
  return out.toString();
}

/// Decifra una stringa esadecimale in plaintext.
String xorDecode(String hexText, String key) {
  final List<int> bytes = [];
  for (int i = 0; i + 1 < hexText.length; i += 2) {
    final int byteVal = int.parse(hexText.substring(i, i + 2), radix: 16);
    final int idx = i ~/ 2;
    bytes.add(byteVal ^ key.codeUnitAt(idx % key.length));
  }
  return utf8.decode(bytes, allowMalformed: true);
}

/// Verifica che una chiave decodifichi correttamente il read endpoint.
Future<bool> _keyValid(Dio dio, String ip, String key) async {
  try {
    final raw = (await dio.get<dynamic>(
      'http://$ip/http-read.json?encrypted=1',
    ))
        .data as String;
    return xorDecode(raw, key).contains('"statusLavatrice"');
  } catch (_) {
    return false;
  }
}

/// Ricava la chiave dal read endpoint via attacco known-plaintext.
Future<String?> _keyFromRead(Dio dio, String ip) async {
  String raw;
  try {
    raw = (await dio.get<dynamic>(
      'http://$ip/http-read.json?encrypted=1',
    ))
        .data as String;
  } catch (_) {
    return null;
  }
  final known = kKnownStatusPrefix;
  final Map<int, int> partial = {};
  for (int i = 0; i < known.length; i++) {
    if (i * 2 + 2 > raw.length) break;
    final int byteVal = int.parse(raw.substring(i * 2, i * 2 + 2), radix: 16);
    final int k = byteVal ^ known.codeUnitAt(i);
    final int pos = i % kKeyLength;
    if (partial.containsKey(pos) && partial[pos] != k) {
      return null; // incoerente
    }
    partial[pos] = k;
  }
  if (partial.length == kKeyLength) {
    return String.fromCharCodes(
      List<int>.generate(kKeyLength, (i) => partial[i]!),
    );
  }
  return null;
}

/// Recupera la chiave di cifratura con strategia a 3 livelli (come Python):
///   1) [cache] chiave fornita dal chiamante se valida
///   2) [BM=1] endpoint http-write.json?encrypted=1&BM=1 con stringa nota
///   3) [fallback] known-plaintext sul read endpoint
///
/// [cachedKey] è la chiave persistita dal chiamante (o null).
/// Ritorna la chiave valida, o solleva [CandyCryptoError].
Future<String> getKey(
  Dio dio,
  String ip, {
  String? cachedKey,
  Duration timeout = const Duration(seconds: 10),
}) async {
  // 1) cache
  if (cachedKey != null && cachedKey.isNotEmpty) {
    if (await _keyValid(dio, ip, cachedKey)) {
      return cachedKey;
    }
  }

  // 2) BM=1
  try {
    final resp = await dio.get<dynamic>(
      'http://$ip/http-write.json?encrypted=1&BM=1',
    ).timeout(timeout);
    final hexIn = resp.data as String;
    final chars = <int>[];
    final n = kKnownResponse.length;
    for (int i = 0; i < kKeyLength && i < n; i++) {
      final int byteVal = int.parse(hexIn.substring(i * 2, i * 2 + 2), radix: 16);
      chars.add(byteVal ^ kKnownResponse.codeUnitAt(i));
    }
    final key = String.fromCharCodes(chars);
    if (await _keyValid(dio, ip, key)) {
      return key;
    }
  } catch (_) {
    // prosegue col fallback
  }

  // 3) fallback known-plaintext
  final key = await _keyFromRead(dio, ip);
  if (key != null) {
    return key;
  }

  throw CandyCryptoError(
    'Impossibile derivare la chiave di cifratura da $ip. '
    'Verifica che la lavatrice sia accesa e raggiungibile.',
  );
}

/// Eccezione del layer crittografico.
class CandyCryptoError implements Exception {
  final String message;
  CandyCryptoError(this.message);
  @override
  String toString() => message;
}
