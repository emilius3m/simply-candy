/// Client HTTP locale per la lavatrice Candy.
///
/// Porting di candy_sendprogram.py: read/write status, start/stop, payload.
/// Tutti i comandi sono GET in chiaro (HTTP) con payload cifrato XOR nell'URL.
library;

import 'dart:convert';
import 'package:dio/dio.dart';

import 'crypto.dart';
import 'programs.dart';

/// Stato decodificato della lavatrice.
class WasherStatus {
  final Map<String, dynamic> raw;
  const WasherStatus(this.raw);

  String? get machMd => raw['MachMd']?.toString();
  String? get pr => raw['Pr']?.toString();
  String? get prCode => raw['PrCode']?.toString();
  String? get prPh => raw['PrPh']?.toString();
  String? get temp => raw['Temp']?.toString();
  String? get spinSp => raw['SpinSp']?.toString();
  String? get sLevel => raw['SLevel']?.toString();
  String? get remTime => raw['RemTime']?.toString();
  String? get delVal => raw['DelVal']?.toString();
  String? get err => raw['Err']?.toString();

  /// Tempo totale residuo in secondi (delay*60 + remaining).
  int get remainingSeconds {
    final del = int.tryParse(delVal ?? '') ?? 0;
    final rem = int.tryParse(remTime ?? '') ?? 0;
    return del * 60 + rem;
  }

  /// Tempo residuo formattato H:MM (ore : minuti).
  String get remainingFormatted {
    final totalMinutes = remainingSeconds ~/ 60;
    final hours = totalMinutes ~/ 60;
    final mins = totalMinutes % 60;
    return '$hours:${mins.toString().padLeft(2, '0')}';
  }

  /// Etichetta leggibile dello stato macchina (MachMd).
  String get machMdLabel {
    switch (machMd) {
      case '0':
        return 'Idle/Remote';
      case '1':
        return 'Inattiva';
      case '2':
        return 'In funzione';
      case '3':
        return 'Pausa';
      case '4':
        return 'Pausa';
      case '5':
        return 'Avvio ritardato';
      case '6':
        return 'Errore';
      case '7':
        return 'Terminato';
      case '9':
        return 'Terminato';
      default:
        return 'Sconosciuto ($machMd)';
    }
  }

  /// Etichetta leggibile della fase (PrPh).
  String get phaseLabel {
    switch (prPh) {
      case '0':
        return 'Attesa';
      case '1':
        return 'Prelavaggio';
      case '2':
        return 'Lavaggio';
      case '3':
        return 'Risciacquo';
      case '4':
        return 'Centrifuga';
      case '5':
        return 'Antipiega';
      case '6':
        return 'Vapore';
      case '7':
        return 'Terminato';
      default:
        return 'Fase $prPh';
    }
  }
}

/// Configura un Dio per traffico HTTP in chiaro verso la lavatrice.
Dio buildLocalDio({Duration timeout = const Duration(seconds: 10)}) {
  return Dio(BaseOptions(
    connectTimeout: timeout,
    receiveTimeout: timeout,
    sendTimeout: timeout,
    responseType: ResponseType.plain,
    validateStatus: (s) => s != null && s < 500,
  ));
}

/// Costruisce il payload di avvio IDENTICO all'app Candy (18 campi, ordine fisso).
String buildStartPayload(
  ProgramDefinition program, {
  int? temp,
  int? spin,
  int? soil,
  Iterable<String> options = const [],
}) {
  validateOverrides(program, temp: temp, spin: spin, soil: soil, options: options);

  final effTemp = temp ?? program.defaults.temp;
  final effSpin = spin ?? program.defaults.spin;
  final effSoil = soil ?? program.defaults.soil;

  if (effSpin % 100 != 0 || program.defaults.spin % 100 != 0) {
    throw OverrideError('Centrifuga non rappresentabile dal protocollo Candy.');
  }

  final masks = computeOptionMasks(options);

  // Ordine fisso derivato da Command.getParameterString() dell'app decompilata.
  final parts = <String>[
    'Write=1',
    'StSt=1',
    'DelVl=0',
    'PrNm=${program.prnm}',
    'PrCode=${program.prcode}',
    'PrStr=${program.prstr}',
    'TmpTgt=$effTemp',
    'SLevTgt=$effSoil',
    'SpdTgt=${effSpin ~/ 100}',
    'OptMsk1=${masks.mask1}',
    'OptMsk2=${masks.mask2}',
    'Lang=1',
    'Stm=${program.defaults.steam}',
    'Dry=${program.defaults.dry}',
    'ED=0',
    'RecipeId=0',
    'StartCheckUp=0',
    'DispTestOn=1',
  ];
  return parts.join('&');
}

/// Client locale: lettura stato, invio comandi, stop.
class CandyLocalClient {
  CandyLocalClient({Dio? dio}) : _dio = dio ?? buildLocalDio();

  final Dio _dio;

  /// Legge lo stato corrente della lavatrice.
  Future<WasherStatus> readStatus(String ip, String key) async {
    final raw = (await _dio.get<dynamic>(
      'http://$ip/http-read.json?encrypted=1',
    ))
        .data as String;
    final decoded = xorDecode(raw, key);
    final json = jsonDecode(decoded) as Map<String, dynamic>;
    final statusLav = json['statusLavatrice'];
    if (statusLav is! Map<String, dynamic>) {
      throw CandyLocalError('Risposta di stato non valida: $decoded');
    }
    return WasherStatus(statusLav);
  }

  /// Invia un payload di comando cifrato.
  ///
  /// GET `http-write.json?encrypted=1&data=HEX` con payload cifrato XOR in hex.
  Future<String> sendCommand(String ip, String key, String payload) async {
    final hexData = xorEncode(payload, key);
    final url = 'http://$ip/http-write.json?encrypted=1&data=$hexData';
    final resp = (await _dio.get<dynamic>(url)).data as String;
    return resp;
  }

  /// Avvia un programma. Ritorna la risposta decifrata del dispositivo.
  Future<String> startProgram(
    String ip,
    String key,
    ProgramDefinition program, {
    int? temp,
    int? spin,
    int? soil,
    Iterable<String> options = const [],
  }) async {
    final payload = buildStartPayload(
      program,
      temp: temp,
      spin: spin,
      soil: soil,
      options: options,
    );
    final respHex = await sendCommand(ip, key, payload);
    try {
      return xorDecode(respHex, key);
    } catch (_) {
      return respHex;
    }
  }

  /// Ferma il ciclo corrente (legge Pr dallo stato, poi StSt=0).
  Future<String> stop(String ip, String key) async {
    final status = await readStatus(ip, key);
    final pr = status.pr ?? '0';
    final payload = 'Write=1&StSt=0&PrNm=$pr';
    final respHex = await sendCommand(ip, key, payload);
    try {
      return xorDecode(respHex, key);
    } catch (_) {
      return respHex;
    }
  }

  void close() => _dio.close();
}

/// Eccezione del client locale.
class CandyLocalError implements Exception {
  final String message;
  CandyLocalError(this.message);
  @override
  String toString() => message;
}
