/// Client cloud Candy: login OAuth (CIAM Salesforce) + fetch appliance/programmi.
///
/// Porting di candy_ciam.py + candy_cloud.py + parte di candy_import_programs.py.
/// Il flusso: beginLogin() -> browser -> callback candy:// -> completeLogin() -> id_token
///           -> fetchAppliances() -> normalizza in ProgramCatalog.
library;

import 'dart:math';
import 'package:dio/dio.dart';

import 'programs.dart';

// ---------------------------------------------------------------------------
// Costanti CIAM (Salesforce) — dal codice Python/decompilato
// ---------------------------------------------------------------------------
const String kLoginServer = 'https://account.candy-home.com/CandyApp';
const String kAuthorizationUrl =
    '$kLoginServer/services/oauth2/authorize/expid_mobileCandy';
const String kTokenUrl = '$kLoginServer/services/oauth2/token';
const String kClientId =
    '3MVG9QDx8IX8nP5T2Ha8ofvlmjKuido4mcuSVCv4GwStG0Lf84ccYQylvDYy9d_'
    'ZLtnyAPzJt4khJoNYn_QVB';
const String kRedirectUri = 'candy://mobilesdk/detect/oauth/done';
const String kScope = 'api id openid refresh_token web';

// ---------------------------------------------------------------------------
// Costanti cloud (Simply-Fi)
// ---------------------------------------------------------------------------
const String kAppliancesUrl =
    'https://simply-fi.herokuapp.com/api/v1/appliances.json?with_programs=1';

const Map<String, String> kAndroidCiamHeaders = {
  'Salesforce-Auth': '1',
  'Brand': '0',
  'Device-Family': 'android',
  'Device-Language': 'it',
  'App-Version-Name': '3.14.1',
  'App-Version-Code': '227',
};

/// Stato di un login in corso (URL + device_id da abbinare al callback).
class PendingLogin {
  final String authorizationUrl;
  final String deviceId;
  const PendingLogin(this.authorizationUrl, this.deviceId);
}

/// Avvia il login: genera un device_id e costruisce l'URL di autorizzazione.
PendingLogin beginLogin({String? deviceId}) {
  final did = deviceId ?? _randomDeviceId();
  // query string in ordine fisso (come il Python)
  final ordered = [
    ('display', 'touch'),
    ('response_type', 'hybrid_token'),
    ('client_id', kClientId),
    ('scope', kScope),
    ('redirect_uri', kRedirectUri),
    ('device_id', did),
  ];
  final qs = ordered.map((e) {
    return '${e.$1}=${Uri.encodeComponent(e.$2)}';
  }).join('&');
  return PendingLogin('$kAuthorizationUrl?$qs', did);
}

String _randomDeviceId() {
  final r = Random.secure();
  final chars = '0123456789abcdef';
  return List.generate(16, (_) => chars[r.nextInt(16)]).join();
}

/// Parsing del callback candy:// -> refresh_token.
/// Valida scheme/netloc/path e preferisce il fragment.
String parseCallback(String callbackUrl) {
  final uri = Uri.tryParse(callbackUrl.trim());
  if (uri == null ||
      uri.scheme != 'candy' ||
      uri.host != 'mobilesdk' ||
      uri.path != '/detect/oauth/done') {
    throw CandyCloudError('Callback Candy non valida.');
  }
  final queryPairs = uri.queryParameters;
  final fragmentPairs = uri.fragment.isEmpty
      ? <String, String>{}
      : Uri.splitQueryString(uri.fragment);

  // preferisce fragment
  final active = fragmentPairs.isNotEmpty ? fragmentPairs : queryPairs;

  if (active.containsKey('error')) {
    throw CandyCloudError('Accesso Candy annullato o rifiutato.');
  }
  final refresh = active['refresh_token'];
  if (refresh == null || refresh.isEmpty) {
    throw CandyCloudError('Callback Candy non valida.');
  }
  return refresh;
}

/// Completa il login: scambia il refresh_token con l'id_token via POST form.
Future<String> completeLogin(
  PendingLogin pending,
  String callbackUrl, {
  Dio? dio,
}) async {
  final refresh = parseCallback(callbackUrl);
  final client = dio ?? Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 5),
    receiveTimeout: const Duration(seconds: 20),
  ));
  try {
    final tokenUrl = '$kTokenUrl?device_id=${pending.deviceId}';
    final resp = await client.post<dynamic>(
      tokenUrl,
      data: {
        'grant_type': 'hybrid_refresh',
        'client_id': kClientId,
        'refresh_token': refresh,
        'format': 'json',
      },
      options: Options(
        contentType: Headers.formUrlEncodedContentType,
        responseType: ResponseType.json,
      ),
    );
    final payload = resp.data;
    if (payload is! Map) {
      throw CandyCloudError('Impossibile ottenere il token Candy.');
    }
    final idToken = payload['id_token'];
    if (idToken is! String || idToken.trim().isEmpty) {
      throw CandyCloudError('Impossibile ottenere il token Candy.');
    }
    return idToken;
  } on DioException {
    throw CandyCloudError('Impossibile ottenere il token Candy.');
  }
}

/// Fetch degli elettrodomestici dal cloud con i relativi programmi.
/// Ritorna la lista grezza di record (lista di mappe).
Future<List<Map<String, dynamic>>> fetchAppliances(
  String idToken, {
  Dio? dio,
}) async {
  if (idToken.trim().isEmpty) {
    throw CandyCloudError('Token Candy non valido.');
  }
  final client = dio ?? Dio();
  try {
    final resp = await client.get<dynamic>(
      kAppliancesUrl,
      options: Options(
        headers: {
          ...kAndroidCiamHeaders,
          'Authorization': 'Bearer $idToken',
        },
        responseType: ResponseType.json,
      ),
    );
    final payload = resp.data;
    if (payload is! List) {
      throw CandyCloudError('Risposta elenco elettrodomestici incompatibile.');
    }
    return payload
        .whereType<Map>()
        .map((e) => e.cast<String, dynamic>())
        .toList();
  } on DioException {
    throw CandyCloudError(
        'Cloud Candy non raggiungibile o risposta incompatibile.');
  }
}

/// Trova le lavatrici BWM che matchano il modello richiesto.
List<Map<String, dynamic>> findMatchingWashers(
  List<Map<String, dynamic>> records,
  String modelQuery,
) {
  final query = _canonicalModelBase(modelQuery);
  final out = <Map<String, dynamic>>[];
  for (final record in records) {
    final appliance = _unwrapAppliance(record);
    if (_isWasher(appliance) &&
        _canonicalModelBase(appliance['appliance_model'] ?? '') == query) {
      out.add(appliance);
    }
  }
  return out;
}

Map<String, dynamic> _unwrapAppliance(Map<String, dynamic> record) {
  final v = record['appliance'];
  if (v is Map) return v.cast<String, dynamic>();
  return record;
}

String _canonicalModel(String value) {
  return value.toUpperCase().replaceAll(RegExp(r'[^A-Z0-9]'), '');
}

String _canonicalModelBase(String value) {
  return _canonicalModel(value.split('/').first);
}

bool _isWasher(Map<String, dynamic> appliance) {
  final type = _canonicalModel(appliance['appliance_type']?.toString() ?? '');
  final model = _canonicalModel(appliance['appliance_model']?.toString() ?? '');
  return {'WM', 'WASHER', 'WASHINGMACHINE'}.contains(type) ||
      model.startsWith('BWM');
}

/// Maschera un appliance id (ultimi 4 char visibili).
String maskApplianceId(Object? value) {
  final raw = value?.toString() ?? '';
  if (raw.isEmpty || raw.length < 4) {
    throw CatalogError('appliance.id: identificatore non valido');
  }
  return '***${raw.substring(raw.length - 4)}';
}

/// Normalizza la risposta cloud di un appliance in un ProgramCatalog.
ProgramCatalog normalizeCatalog(
  Map<String, dynamic> appliance, {
  required String importedAt,
}) {
  final rawPrograms = appliance['programs'];
  if (rawPrograms is! List || rawPrograms.isEmpty) {
    throw CatalogError('appliance.programs: lista non vuota obbligatoria');
  }
  final programs = <ProgramDefinition>[];
  final usedNames = <String>{};
  for (final rawProgram in rawPrograms) {
    if (rawProgram is! Map) {
      throw CatalogError('program: record non valido');
    }
    final p = _normalizeProgram(rawProgram.cast<String, dynamic>());
    var name = p.name;
    if (usedNames.contains(name)) {
      name = '${p.name}-${p.prnm}';
    }
    if (usedNames.contains(name)) {
      throw CatalogError('program.name duplicato: $name');
    }
    usedNames.add(name);
    if (name != p.name) {
      programs.add(ProgramDefinition(
        name: name,
        prnm: p.prnm,
        prcode: p.prcode,
        prstr: p.prstr,
        defaults: p.defaults,
        allowed: p.allowed,
        source: p.source,
      ));
    } else {
      programs.add(p);
    }
  }
  final model = appliance['appliance_model']?.toString();
  if (model == null || model.isEmpty) {
    throw CatalogError('appliance.appliance_model: stringa obbligatoria');
  }
  return ProgramCatalog(
    schemaVersion: 1,
    source: 'candy-cloud',
    appliance: ApplianceInfo(
      model: model,
      idMasked: maskApplianceId(appliance['id'] ?? appliance['uid']),
    ),
    importedAt: importedAt,
    programs: programs,
  );
}

ProgramDefinition _normalizeProgram(Map<String, dynamic> rawRecord) {
  final raw = (rawRecord['program'] is Map)
      ? (rawRecord['program'] as Map).cast<String, dynamic>()
      : rawRecord;
  final params = _flattenParameters(raw);
  final cloudName = raw['name']?.toString();
  if (cloudName == null || cloudName.isEmpty) {
    throw CatalogError('program.name: stringa obbligatoria');
  }
  final selector = _reqInt(params, 'selector_position');
  final code = _reqInt(params, 'pr_code');
  final temp = _reqInt(params, 'default_temperature');
  final spin = _reqInt(params, 'default_spin_speed');
  final soil = _reqInt(params, 'default_soil_level');
  final steam = params.containsKey('steam') ? _reqInt(params, 'steam') : 0;
  final dry = params.containsKey('dry') ? _reqInt(params, 'dry') : 0;
  final shortName = cloudName.startsWith('DUAL_WM_WD_PROGRAM_NAME_')
      ? cloudName.substring('DUAL_WM_WD_PROGRAM_NAME_'.length)
      : cloudName;
  final slug = shortName
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9]+'), '-')
      .replaceAll(RegExp(r'^-+|-+$'), '');
  return ProgramDefinition(
    name: slug,
    prnm: selector,
    prcode: code,
    prstr: cloudName,
    defaults: ProgramDefaults(
      temp: temp,
      spin: spin,
      soil: soil,
      steam: steam,
      dry: dry,
    ),
    allowed: ProgramAllowed(
      temp: _allowedInts(params, 'allowed_temperatures', temp),
      spin: _allowedInts(params, 'allowed_spin_speeds', spin),
      soil: _allowedInts(params, 'allowed_soil_levels', soil),
      options: _allowedOptions(params),
    ),
    source: 'candy-cloud',
  );
}

Map<String, String> _flattenParameters(Map<String, dynamic> raw) {
  final rawParams = raw['command_parameters'];
  if (rawParams is! List) {
    throw CatalogError('program.command_parameters: lista obbligatoria');
  }
  final out = <String, String>{};
  for (var i = 0; i < rawParams.length; i++) {
    final rec = rawParams[i];
    if (rec is! Map) {
      throw CatalogError('program.command_parameters[$i]: record non valido');
    }
    final v = (rec['command_parameter'] is Map)
        ? (rec['command_parameter'] as Map).cast<String, dynamic>()
        : rec.cast<String, dynamic>();
    final name = v['name'];
    var validation = v['validation'];
    if (name is! String || name.isEmpty) {
      throw CatalogError('program.command_parameters[$i].name: stringa non vuota obbligatoria');
    }
    // normalizza come il Python (numeri/bool/null -> stringa)
    if (validation == null) {
      validation = '';
    } else if (validation is bool) {
      validation = validation ? '1' : '0';
    } else if (validation is num) {
      validation = validation.toString();
    } else if (validation is! String) {
      throw CatalogError('program.command_parameters[$i].validation: tipo non valido');
    }
    if (out.containsKey(name)) {
      throw CatalogError('command_parameters.$name: nome duplicato');
    }
    if (validation == '') continue;
    out[name] = validation;
  }
  return out;
}

int _reqInt(Map<String, String> params, String name) {
  final v = params[name];
  if (v == null) {
    throw CatalogError('command_parameters.$name: intero obbligatorio');
  }
  return int.tryParse(v) ??
      (throw CatalogError('command_parameters.$name: intero obbligatorio'));
}

List<int> _allowedInts(Map<String, String> params, String name, int def) {
  final raw = params[name];
  if (raw == null) return [def];
  final values = raw
      .split(',')
      .map((s) => int.tryParse(s.trim()))
      .whereType<int>()
      .toList();
  // dedup保 持 ordine
  final seen = <int>{};
  final out = <int>[];
  for (final v in values) {
    if (seen.add(v)) out.add(v);
  }
  if (out.isEmpty || !out.contains(def)) {
    throw CatalogError('command_parameters.$name: default non ammesso');
  }
  return out;
}

List<String> _allowedOptions(Map<String, String> params) {
  final m1 = int.tryParse(params['available_options'] ?? '0') ?? 0;
  final m2 = int.tryParse(params['available_options2'] ?? '0') ?? 0;
  if (m1 < 0 || m2 < 0) {
    throw CatalogError('command_parameters.available_options: valore negativo');
  }
  final known1 = kOptionBits.values
      .where((e) => e.mask == 1)
      .fold<int>(0, (a, e) => a | e.bit);
  final known2 = kOptionBits.values
      .where((e) => e.mask == 2)
      .fold<int>(0, (a, e) => a | e.bit);
  if (m1 & ~known1 != 0) {
    throw CatalogError(
        'command_parameters.available_options: bit sconosciuti (OptMsk1)');
  }
  if (m2 & ~known2 != 0) {
    throw CatalogError(
        'command_parameters.available_options: bit sconosciuti (OptMsk2)');
  }
  final out = <String>[];
  for (final entry in kOptionBits.entries) {
    final value = entry.value.mask == 1 ? m1 : m2;
    if (value & entry.value.bit != 0) out.add(entry.key);
  }
  return out;
}

/// Eccezione cloud.
class CandyCloudError implements Exception {
  final String message;
  CandyCloudError(this.message);
  @override
  String toString() => message;
}
