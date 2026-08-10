/// Modelli del catalogo programmi Candy (porting di candy_programs.py).
///
/// Classi immutabili + validazione fedele allo schema Python.
library;

import 'package:json_annotation/json_annotation.dart';

part 'programs.g.dart';

/// Mappatura nome opzione -> (maschera, bit).
///
/// Il protocollo Candy usa DUE maschere: OptMsk1 (bit 0-7) e OptMsk2
/// (bit 0-N della seconda maschera). Valori ricavati dal codice decompilato
/// dell'app (Command.Param.OPTION_MASK_1/2, isZoom()).
class OptionBit {
  final int mask; // 1 = OptMsk1, 2 = OptMsk2
  final int bit;
  const OptionBit(this.mask, this.bit);
}

const Map<String, OptionBit> kOptionBits = {
  // --- OptMsk1 (mask 1) ---
  'prewash': OptionBit(1, 1),
  'hygiene': OptionBit(1, 2),
  'anti_crease': OptionBit(1, 4),
  'good_night': OptionBit(1, 8),
  'extra_rinse_1': OptionBit(1, 16),
  'extra_rinse_2': OptionBit(1, 32),
  'extra_rinse_3': OptionBit(1, 64),
  'aquaplus': OptionBit(1, 128),
  // --- OptMsk2 (mask 2) ---
  'zoom': OptionBit(2, 1),
};

/// Etichette italiane per la UI (escluso zoom, mostrato come identificatore).
const Map<String, String> kOptionLabels = {
  'prewash': 'Prelavaggio',
  'hygiene': 'Hygiene+',
  'anti_crease': 'Antipiega',
  'good_night': 'Good Night',
  'extra_rinse_1': 'Risciacquo extra 1',
  'extra_rinse_2': 'Risciacquo extra 2',
  'extra_rinse_3': 'Risciacquo extra 3',
  'aquaplus': 'Aqua Plus',
  'zoom': 'Zoom',
};

/// Source ammesse per i programmi/catalogo.
const Set<String> kAllowedSources = {'candy-cloud', 'local-verified'};

@JsonSerializable(explicitToJson: true, fieldRename: FieldRename.snake)
class ProgramDefaults {
  final int temp;
  final int spin; // in rpm (es. 1400); diviso per 100 nel payload
  final int soil;
  final int steam;
  final int dry;

  const ProgramDefaults({
    required this.temp,
    required this.spin,
    required this.soil,
    required this.steam,
    required this.dry,
  });

  factory ProgramDefaults.fromJson(Map<String, dynamic> json) =>
      _$ProgramDefaultsFromJson(json);
  Map<String, dynamic> toJson() => _$ProgramDefaultsToJson(this);
}

@JsonSerializable(explicitToJson: true, fieldRename: FieldRename.snake)
class ProgramAllowed {
  final List<int> temp;
  final List<int> spin;
  final List<int> soil;
  final List<String> options;

  const ProgramAllowed({
    required this.temp,
    required this.spin,
    required this.soil,
    required this.options,
  });

  factory ProgramAllowed.fromJson(Map<String, dynamic> json) =>
      _$ProgramAllowedFromJson(json);
  Map<String, dynamic> toJson() => _$ProgramAllowedToJson(this);
}

@JsonSerializable(explicitToJson: true, fieldRename: FieldRename.snake)
class ProgramDefinition {
  final String name;
  final int prnm;
  final int prcode;
  final String prstr;
  final ProgramDefaults defaults;
  final ProgramAllowed allowed;
  final String source;

  const ProgramDefinition({
    required this.name,
    required this.prnm,
    required this.prcode,
    required this.prstr,
    required this.defaults,
    required this.allowed,
    required this.source,
  });

  factory ProgramDefinition.fromJson(Map<String, dynamic> json) =>
      _$ProgramDefinitionFromJson(json);
  Map<String, dynamic> toJson() => _$ProgramDefinitionToJson(this);
}

@JsonSerializable(explicitToJson: true, fieldRename: FieldRename.snake)
class ApplianceInfo {
  final String model;
  @JsonKey(name: 'id_masked')
  final String idMasked;

  const ApplianceInfo({required this.model, required this.idMasked});

  factory ApplianceInfo.fromJson(Map<String, dynamic> json) =>
      _$ApplianceInfoFromJson(json);
  Map<String, dynamic> toJson() => _$ApplianceInfoToJson(this);
}

@JsonSerializable(explicitToJson: true, fieldRename: FieldRename.snake)
class ProgramCatalog {
  @JsonKey(name: 'schema_version')
  final int schemaVersion;
  final String source;
  final ApplianceInfo appliance;
  @JsonKey(name: 'imported_at')
  final String importedAt;
  final List<ProgramDefinition> programs;

  const ProgramCatalog({
    required this.schemaVersion,
    required this.source,
    required this.appliance,
    required this.importedAt,
    required this.programs,
  });

  factory ProgramCatalog.fromJson(Map<String, dynamic> json) =>
      _$ProgramCatalogFromJson(json);
  Map<String, dynamic> toJson() => _$ProgramCatalogToJson(this);

  /// Cerca un programma per nome (slug).
  ProgramDefinition byName(String name) {
    for (final p in programs) {
      if (p.name == name) return p;
    }
    throw CatalogError('Programma sconosciuto: $name');
  }
}

/// Eccezioni del catalogo (parallelo a candy_programs.py).
class CatalogError implements Exception {
  final String message;
  CatalogError(this.message);
  @override
  String toString() => message;
}

class OverrideError implements Exception {
  final String message;
  OverrideError(this.message);
  @override
  String toString() => message;
}

/// Valida un override contro i vincoli del programma.
void validateOverrides(
  ProgramDefinition program, {
  int? temp,
  int? spin,
  int? soil,
  Iterable<String> options = const [],
}) {
  void checkInt(int? value, List<int> allowed, String label) {
    if (value != null && !allowed.contains(value)) {
      throw OverrideError(
          '$label non ammessa per il programma ${program.name}');
    }
  }

  checkInt(temp, program.allowed.temp, 'temperatura');
  checkInt(spin, program.allowed.spin, 'centrifuga');
  checkInt(soil, program.allowed.soil, 'livello di sporco');

  for (final opt in options) {
    if (!program.allowed.options.contains(opt)) {
      throw OverrideError(
          'opzione non ammessa per il programma ${program.name}');
    }
  }
}

/// Calcola le due maschere opzioni da una lista di nomi.
({int mask1, int mask2}) computeOptionMasks(Iterable<String> options) {
  int m1 = 0, m2 = 0;
  for (final name in options) {
    final ob = kOptionBits[name];
    if (ob == null) {
      throw OverrideError('opzione sconosciuta: $name');
    }
    if (ob.mask == 1) {
      m1 |= ob.bit;
    } else {
      m2 |= ob.bit;
    }
  }
  return (mask1: m1, mask2: m2);
}
