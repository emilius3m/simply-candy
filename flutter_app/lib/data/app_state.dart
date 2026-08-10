/// Stato centrale dell'app (Provider): IP lavatrice, chiave cache, catalogo.
///
/// Persiste IP e chiave su file; il catalogo viene caricato dal file
/// `programs.json` persistito o, in fallback, dall'asset bundled.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:path_provider/path_provider.dart';

import '../core/programs.dart';
import 'favorites.dart';

/// Nome del file di catalogo persistito.
const String kCatalogFileName = 'programs.json';
/// Nome del file di impostazioni (IP + chiave cache).
const String kSettingsFileName = 'candy_settings.json';

class AppState extends ChangeNotifier {
  AppState();

  final FavoritesStore _favStore = FavoritesStore();

  String _candyIp = '192.168.1.235';
  String? _cachedKey;
  ProgramCatalog? _catalog;
  List<FavoriteWash> _favorites = [];
  bool _loading = true;
  String? _loadError;

  String get candyIp => _candyIp;
  String? get cachedKey => _cachedKey;
  ProgramCatalog? get catalog => _catalog;
  List<FavoriteWash> get favorites => _favorites;
  bool get isLoading => _loading;
  String? get loadError => _loadError;

  /// Carica lo stato all'avvio (settings + catalogo + preferiti).
  Future<void> load() async {
    _loading = true;
    _loadError = null;
    notifyListeners();
    try {
      await _loadSettings();
      await _loadCatalog();
      _favorites = await _favStore.load();
    } catch (e) {
      _loadError = e.toString();
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  /// Imposta l'IP della lavatrice e persiste.
  Future<void> setCandyIp(String ip) async {
    _candyIp = ip;
    notifyListeners();
    await _persistSettings();
  }

  /// Imposta (e persiste) la chiave di cifratura cacheata.
  Future<void> setCachedKey(String? key) async {
    _cachedKey = key;
    notifyListeners();
    await _persistSettings();
  }

  /// Sostituisce il catalogo (es. dopo import dal cloud) e lo persiste.
  Future<void> setCatalog(ProgramCatalog catalog) async {
    _catalog = catalog;
    notifyListeners();
    await _persistCatalog(catalog);
  }

  // -- Preferiti -----------------------------------------------------------
  /// Aggiunge un preferito e lo persiste.
  Future<void> addFavorite(FavoriteWash fav) async {
    _favorites = [..._favorites, fav];
    notifyListeners();
    await _favStore.save(_favorites);
  }

  /// Rimuove un preferito per id e persiste.
  Future<void> removeFavorite(String id) async {
    _favorites = _favorites.where((f) => f.id != id).toList();
    notifyListeners();
    await _favStore.save(_favorites);
  }

  // -- settings (IP + chiave) ----------------------------------------------
  Future<void> _loadSettings() async {
    try {
      final file = await _settingsFile();
      if (!await file.exists()) return;
      final raw = await file.readAsString();
      final json = jsonDecode(raw) as Map<String, dynamic>;
      final ip = json['ip'];
      if (ip is String && ip.isNotEmpty) _candyIp = ip;
      final key = json['key'];
      if (key is String && key.isNotEmpty) _cachedKey = key;
    } catch (_) {
      // ignora file corrotto: usa default
    }
  }

  Future<void> _persistSettings() async {
    try {
      final file = await _settingsFile();
      await file.writeAsString(jsonEncode({
        'ip': _candyIp,
        if (_cachedKey != null) 'key': _cachedKey,
      }));
    } catch (_) {
      // best-effort
    }
  }

  Future<File> _settingsFile() async {
    final dir = await getApplicationSupportDirectory();
    return File('${dir.path}/$kSettingsFileName');
  }

  // -- catalogo -------------------------------------------------------------
  Future<void> _loadCatalog() async {
    // 1) prova il file persistito (eventualmente aggiornato dal cloud)
    try {
      final file = await _catalogFile();
      if (await file.exists()) {
        final raw = await file.readAsString();
        _catalog = _parseCatalog(raw);
        return;
      }
    } catch (_) {
      // falla al fallback
    }
    // 2) fallback: asset bundled (19 programmi del modello di riferimento)
    try {
      final raw = await rootBundle.loadString('assets/$kCatalogFileName');
      _catalog = _parseCatalog(raw);
    } catch (e) {
      _loadError = 'Catalogo non disponibile: $e';
    }
  }

  Future<void> _persistCatalog(ProgramCatalog catalog) async {
    try {
      final file = await _catalogFile();
      await file.writeAsString(jsonEncode(catalog.toJson()));
    } catch (_) {
      // best-effort
    }
  }

  Future<File> _catalogFile() async {
    final dir = await getApplicationSupportDirectory();
    return File('${dir.path}/$kCatalogFileName');
  }

  ProgramCatalog _parseCatalog(String raw) {
    final json = jsonDecode(raw) as Map<String, dynamic>;
    return ProgramCatalog.fromJson(json);
  }
}
