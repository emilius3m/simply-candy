/// Lavaggi preferiti: configurazioni personali salvate dall'utente.
///
/// Un preferito associa un programma del catalogo a un set di override
/// (temperatura, centrifuga, livello sporco) e opzioni, più un nome
/// personalizzato. Si avvia con un tap.
library;

import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

const String kFavoritesFileName = 'candy_favorites.json';

/// Un lavaggio preferito salvato dall'utente.
class FavoriteWash {
  final String id;            // identificatore univoco (timestamp-based)
  final String customName;    // nome scelto dall'utente (es. "Bianchi 60° con prelavaggio")
  final String programName;   // slug del programma nel catalogo
  final int? temp;
  final int? spin;
  final int? soil;
  final List<String> options;

  const FavoriteWash({
    required this.id,
    required this.customName,
    required this.programName,
    this.temp,
    this.spin,
    this.soil,
    this.options = const [],
  });

  Map<String, dynamic> toJson() => {
        'id': id,
        'custom_name': customName,
        'program_name': programName,
        if (temp != null) 'temp': temp,
        if (spin != null) 'spin': spin,
        if (soil != null) 'soil': soil,
        'options': options,
      };

  factory FavoriteWash.fromJson(Map<String, dynamic> json) => FavoriteWash(
        id: json['id'] as String,
        customName: json['custom_name'] as String,
        programName: json['program_name'] as String,
        temp: json['temp'] as int?,
        spin: json['spin'] as int?,
        soil: json['soil'] as int?,
        options: (json['options'] as List<dynamic>? ?? [])
            .map((e) => e as String)
            .toList(),
      );

  FavoriteWash copyWith({
    String? customName,
    int? temp,
    int? spin,
    int? soil,
    List<String>? options,
  }) =>
      FavoriteWash(
        id: id,
        customName: customName ?? this.customName,
        programName: programName,
        temp: temp ?? this.temp,
        spin: spin ?? this.spin,
        soil: soil ?? this.soil,
        options: options ?? this.options,
      );
}

/// Persistenza dei preferiti su file JSON.
class FavoritesStore {
  Future<List<FavoriteWash>> load() async {
    try {
      final file = await _file();
      if (!await file.exists()) return [];
      final raw = await file.readAsString();
      final list = jsonDecode(raw) as List<dynamic>;
      return list
          .map((e) => FavoriteWash.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return [];
    }
  }

  Future<void> save(List<FavoriteWash> favorites) async {
    try {
      final file = await _file();
      await file.writeAsString(jsonEncode(favorites.map((f) => f.toJson()).toList()));
    } catch (_) {
      // best-effort
    }
  }

  Future<File> _file() async {
    final dir = await getApplicationSupportDirectory();
    return File('${dir.path}/$kFavoritesFileName');
  }
}
