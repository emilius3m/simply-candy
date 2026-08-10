/// Candy lavatrice - app Flutter multi-piattaforma.
///
/// Parla direttamente con la lavatrice (HTTP locale, nessun server).
/// Catalogo programmi importato dal cloud o pre-caricato come asset.
library;

import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'core/candy_local.dart';
import 'core/candy_cloud.dart';
import 'core/catalog_ui.dart';
import 'core/crypto.dart';
import 'core/discovery.dart';
import 'core/programs.dart';
import 'data/app_state.dart';
import 'data/favorites.dart';
import 'widgets/washer_panel.dart';

void main() {
  runApp(const CandyApp());
}

class CandyApp extends StatelessWidget {
  const CandyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AppState()..load(),
      child: MaterialApp(
        title: 'Candy Lavatrice',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          brightness: Brightness.dark,
          colorScheme: const ColorScheme.dark(
            primary: Color(0xFF38bdf8),
            surface: Color(0xFF1e293b),
          ),
          scaffoldBackgroundColor: const Color(0xFF0f172a),
          cardColor: const Color(0xFF1e293b),
          useMaterial3: true,
        ),
        home: const HomeScreen(),
      ),
    );
  }
}

/// Schermata principale con navigazione tra Stato / Avvio / Impostazioni.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    if (app.isLoading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    final screens = [
      const StatusTab(),
      const StartTab(),
      const SettingsTab(),
    ];
    return Scaffold(
      body: screens[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Stato',
          ),
          NavigationDestination(
            icon: Icon(Icons.local_laundry_service_outlined),
            selectedIcon: Icon(Icons.local_laundry_service),
            label: 'Avvio',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: 'Impostazioni',
          ),
        ],
      ),
    );
  }
}

// ===========================================================================
// TAB STATO
// ===========================================================================
class StatusTab extends StatefulWidget {
  const StatusTab({super.key});
  @override
  State<StatusTab> createState() => _StatusTabState();
}

class _StatusTabState extends State<StatusTab> {
  WasherStatus? _status;
  bool _online = false;
  bool _loading = false;
  bool _stopping = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    // Prova la connessione automatica all'avvio
    WidgetsBinding.instance.addPostFrameCallback((_) => _refresh());
  }

  Future<void> _refresh() async {
    final app = context.read<AppState>();
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final dio = buildLocalDio();
      final key = await getKey(dio, app.candyIp, cachedKey: app.cachedKey);
      await app.setCachedKey(key);
      final client = CandyLocalClient(dio: dio);
      final s = await client.readStatus(app.candyIp, key);
      setState(() {
        _status = s;
        _online = true;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _online = false;
        _loading = false;
        _error = e.toString();
      });
    }
  }

  bool get _running => _status?.machMd == '2';

  Future<void> _stop() async {
    final app = context.read<AppState>();
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Fermare il ciclo?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Annulla')),
          TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Ferma')),
        ],
      ),
    );
    if (ok != true) return;
    setState(() => _stopping = true);
    try {
      final dio = buildLocalDio();
      final key = await getKey(dio, app.candyIp, cachedKey: app.cachedKey);
      await app.setCachedKey(key);
      final client = CandyLocalClient(dio: dio);
      await client.stop(app.candyIp, key);
      // Refresh stato dopo lo stop
      await _refresh();
    } catch (e) {
      setState(() => _error = 'Stop fallito: $e');
    } finally {
      setState(() => _stopping = false);
    }
  }

  /// Risolve il nome italiano del programma corrente dal catalogo.
  /// Cerca prima per `prnm` (Pr), poi per `prcode` come fallback.
  String? _resolveProgramName(WasherStatus? s, ProgramCatalog? catalog) {
    if (s == null || catalog == null) return null;
    final pr = s.pr;
    final code = s.prCode;
    ProgramDefinition? match;
    if (pr != null) {
      try {
        match = catalog.programs.firstWhere((p) => p.prnm.toString() == pr);
      } catch (_) {
        match = null;
      }
    }
    // per programmi rapidi che condividono prnm, prova a disambiguare col SLevel
    if (match != null && pr != null) {
      final candidates = catalog.programs.where((p) => p.prnm.toString() == pr);
      final soil = s.sLevel;
      if (soil != null) {
        for (final c in candidates) {
          if (c.defaults.soil.toString() == soil) {
            match = c;
            break;
          }
        }
      }
    }
    match ??= () {
      if (code == null) return null;
      try {
        return catalog.programs.firstWhere((p) => p.prcode.toString() == code);
      } catch (_) {
        return null;
      }
    }();
    return match == null ? null : italianName(match);
  }

  @override
  Widget build(BuildContext context) {
    final s = _status;
    final app = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(
        title: Row(children: [
          const Text('🫧 Candy'),
          const SizedBox(width: 8),
          // spia online/offline lampeggiante
          _OnlineLed(online: _online, running: _running),
        ]),
        actions: [
          IconButton(
            icon: _loading
                ? const SizedBox(
                    width: 20, height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh),
            onPressed: _loading ? null : _refresh,
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // --- Pannello frontale realistico della lavatrice ---
          WasherPanel(
            running: _running,
            online: _online,
            statusLabel: s?.machMdLabel,
            phaseLabel: s?.phaseLabel,
            remainingTime: s?.remainingFormatted,
            temp: s?.temp,
            spinSp: s?.spinSp,
            programNumber: s?.pr,
            programName: _resolveProgramName(s, app.catalog),
            hasError: s != null && s.err != '0',
          ),
          const SizedBox(height: 16),
          // --- Pulsante STOP (visibile solo se in funzione) ---
          if (_running)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: FilledButton.icon(
                onPressed: _stopping ? null : _stop,
                icon: _stopping
                    ? const SizedBox(
                        width: 18, height: 18,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.stop_circle),
                label: Text(_stopping ? 'Arresto…' : 'Ferma lavaggio'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFdc2626),
                  foregroundColor: Colors.white,
                  minimumSize: const Size.fromHeight(48),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
          // --- Errore di connessione ---
          if (!_online && _error != null)
            Card(
              color: const Color(0xFF2a1517),
              child: ListTile(
                leading: const Icon(Icons.wifi_off, color: Colors.red),
                title: const Text('Lavatrice offline'),
                subtitle: Text(_error!, style: const TextStyle(fontSize: 12)),
              ),
            ),
          if (s == null && !_loading && _error == null)
            const Padding(
              padding: EdgeInsets.all(32),
              child: Center(
                  child: Text('Premi ↻ per aggiornare lo stato.',
                      style: TextStyle(color: Colors.white54))),
            ),
        ],
      ),
    );
  }
}

Widget sectionTitle(String text) => Padding(
      padding: const EdgeInsets.only(top: 8, bottom: 4),
      child: Text(text.toUpperCase(),
          style: const TextStyle(
              color: Color(0xFF38bdf8),
              fontSize: 13,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.5)),
    );

class StatCard extends StatelessWidget {
  final String label;
  final String value;
  final bool big;
  const StatCard(this.label, this.value, {super.key, this.big = false});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label.toUpperCase(),
                style: const TextStyle(fontSize: 11, color: Colors.white54)),
            const SizedBox(height: 2),
            Text(value,
                style: TextStyle(
                    fontSize: big ? 28 : 20, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}

/// Spia LED di connessione (lampeggia quando in funzione).
class _OnlineLed extends StatefulWidget {
  final bool online;
  final bool running;
  const _OnlineLed({required this.online, required this.running});

  @override
  State<_OnlineLed> createState() => _OnlineLedState();
}

class _OnlineLedState extends State<_OnlineLed>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 900));
    _update();
  }

  @override
  void didUpdateWidget(covariant _OnlineLed old) {
    super.didUpdateWidget(old);
    if (old.running != widget.running) _update();
  }

  void _update() {
    if (widget.running) {
      _c.repeat(reverse: true);
    } else {
      _c.stop();
      _c.value = widget.online ? 1.0 : 0.0;
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.online
        ? (widget.running ? Colors.orange : Colors.green)
        : Colors.red;
    return AnimatedBuilder(
      animation: _c,
      builder: (context, _) {
        final alpha = widget.running ? _c.value : 1.0;
        return Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color.withValues(alpha: 0.3 + 0.7 * alpha),
            boxShadow: [
              BoxShadow(
                  color: color.withValues(alpha: 0.6 * alpha),
                  blurRadius: 8,
                  spreadRadius: 1),
            ],
          ),
        );
      },
    );
  }
}

// ===========================================================================
// ===========================================================================
// TAB AVVIO
// ===========================================================================
/// Schermata avvio: sezione Preferiti (avvio rapido) + griglia programmi
/// con nome italiano + editor con override e "salva come preferito".
class StartTab extends StatefulWidget {
  const StartTab({super.key});
  @override
  State<StartTab> createState() => _StartTabState();
}

class _StartTabState extends State<StartTab> {
  /// Programma in corso di editing (null = nessuno selezionato).
  ProgramDefinition? _program;
  final _tempCtrl = TextEditingController();
  final _spinCtrl = TextEditingController();
  final _soilCtrl = TextEditingController();
  final _options = <String>{};
  String _msg = '';

  void _selectProgram(ProgramDefinition p) {
    setState(() {
      _program = p;
      _options.clear();
      _tempCtrl.text = p.defaults.temp.toString();
      _spinCtrl.text = p.defaults.spin.toString();
      _soilCtrl.text = p.defaults.soil.toString();
      _msg = '';
    });
  }

  ({int? temp, int? spin, int? soil, Set<String> options}) _currentOverrides() {
    return (
      temp: int.tryParse(_tempCtrl.text),
      spin: int.tryParse(_spinCtrl.text),
      soil: int.tryParse(_soilCtrl.text),
      options: Set<String>.from(_options),
    );
  }

  Future<void> _startWith({
    required String programName,
    int? temp,
    int? spin,
    int? soil,
    Iterable<String> options = const [],
    String? labelForMsg,
  }) async {
    final app = context.read<AppState>();
    final catalog = app.catalog;
    if (catalog == null) {
      setState(() => _msg = 'Catalogo non disponibile.');
      return;
    }
    ProgramDefinition p;
    try {
      p = catalog.byName(programName);
    } catch (_) {
      setState(() => _msg = 'Programma "$programName" non trovato nel catalogo.');
      return;
    }
    setState(() => _msg = 'Invio comando…');
    try {
      final dio = buildLocalDio();
      final key = await getKey(dio, app.candyIp, cachedKey: app.cachedKey);
      await app.setCachedKey(key);
      final client = CandyLocalClient(dio: dio);
      await client.startProgram(
        app.candyIp,
        key,
        p,
        temp: temp,
        spin: spin,
        soil: soil,
        options: options,
      );
      setState(() => _msg = '✓ Avviato: ${labelForMsg ?? italianName(p)}');
    } catch (e) {
      setState(() => _msg = '✗ $e');
    }
  }

  Future<void> _stop() async {
    final app = context.read<AppState>();
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Fermare il ciclo?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Annulla')),
          TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Ferma')),
        ],
      ),
    );
    if (ok != true) return;
    setState(() => _msg = 'Invio stop…');
    try {
      final dio = buildLocalDio();
      final key = await getKey(dio, app.candyIp, cachedKey: app.cachedKey);
      await app.setCachedKey(key);
      final client = CandyLocalClient(dio: dio);
      await client.stop(app.candyIp, key);
      setState(() => _msg = '■ Stop inviato.');
    } catch (e) {
      setState(() => _msg = '✗ $e');
    }
  }

  Future<void> _saveFavorite() async {
    final p = _program;
    if (p == null) {
      setState(() => _msg = 'Seleziona prima un programma.');
      return;
    }
    final ov = _currentOverrides();
    // chiede il nome personalizzato
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) {
        final ctrl = TextEditingController(text: italianName(p));
        return AlertDialog(
          title: const Text('Salva come preferito'),
          content: TextField(
            controller: ctrl,
            autofocus: true,
            decoration: const InputDecoration(
                labelText: 'Nome', border: OutlineInputBorder()),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx), child: const Text('Annulla')),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, ctrl.text.trim()),
              child: const Text('Salva'),
            ),
          ],
        );
      },
    );
    if (name == null || name.isEmpty) return;
    final fav = FavoriteWash(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      customName: name,
      programName: p.name,
      temp: ov.temp,
      spin: ov.spin,
      soil: ov.soil,
      options: ov.options.toList(),
    );
    await context.read<AppState>().addFavorite(fav);
    setState(() => _msg = '★ Preferito "$name" salvato.');
  }

  @override
  void dispose() {
    _tempCtrl.dispose();
    _spinCtrl.dispose();
    _soilCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final catalog = app.catalog;
    if (catalog == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Avvio')),
        body: const Center(
            child: Text('Catalogo programmi non disponibile.\n'
                'Vai in Impostazioni per importarlo dal cloud.',
                textAlign: TextAlign.center)),
      );
    }
    // programmi di lavaggio (esclusi servizio), ordinati per categoria poi nome
    final washPrograms = catalog.programs.where(isWashProgram).toList()
      ..sort((a, b) {
        final ca = categoryOf(a).index;
        final cb = categoryOf(b).index;
        if (ca != cb) return ca.compareTo(cb);
        return italianName(a).compareTo(italianName(b));
      });

    return Scaffold(
      appBar: AppBar(
        title: const Text('Avvio'),
        actions: [
          IconButton(
            tooltip: 'Ferma ciclo',
            onPressed: _stop,
            icon: const Icon(Icons.stop_circle_outlined),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // --- Sezione Preferiti ---
          if (app.favorites.isNotEmpty) ...[
            sectionTitle('Preferiti'),
            const SizedBox(height: 4),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                for (final fav in app.favorites) _FavoriteChip(fav),
              ],
            ),
            const SizedBox(height: 20),
          ],
          // --- Editor del programma selezionato ---
          if (_program != null) ...[
            _ProgramEditor(
              program: _program!,
              tempCtrl: _tempCtrl,
              spinCtrl: _spinCtrl,
              soilCtrl: _soilCtrl,
              options: _options,
              onOptionToggle: (opt, v) => setState(() {
                if (v) {
                  _options.add(opt);
                } else {
                  _options.remove(opt);
                }
              }),
              onStart: () {
                final ov = _currentOverrides();
                _startWith(
                  programName: _program!.name,
                  temp: ov.temp,
                  spin: ov.spin,
                  soil: ov.soil,
                  options: ov.options,
                );
              },
              onSaveFavorite: _saveFavorite,
              onClose: () => setState(() => _program = null),
            ),
            const SizedBox(height: 12),
          ],
          if (_msg.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(_msg,
                  style: TextStyle(
                      color: _msg.startsWith('✓')
                          ? Colors.green
                          : _msg.startsWith('★')
                              ? const Color(0xFFf59e0b)
                              : Colors.orange)),
            ),
          // --- Lista programmi come schede ---
          sectionTitle('Programmi'),
          const SizedBox(height: 8),
          GridView.count(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisCount: MediaQuery.of(context).size.width > 600 ? 3 : 2,
            mainAxisSpacing: 12,
            crossAxisSpacing: 12,
            childAspectRatio: 1.0,
            children: [
              for (final p in washPrograms) _ProgramCard(p, onTap: () => _selectProgram(p)),
            ],
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

/// Scheda programma con nome italiano, icona categoria e parametri.
class _ProgramCard extends StatelessWidget {
  final ProgramDefinition program;
  final VoidCallback onTap;
  const _ProgramCard(this.program, {required this.onTap});

  @override
  Widget build(BuildContext context) {
    final accent = colorFor(program);
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Icon(iconFor(program), color: accent, size: 20),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    italianName(program),
                    style: const TextStyle(
                        fontSize: 15, fontWeight: FontWeight.w600),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ]),
              const Spacer(),
              Text(
                _paramsLine(program),
                style: const TextStyle(fontSize: 12, color: Colors.white54),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _paramsLine(ProgramDefinition p) {
    final t = p.defaults.temp == 255 ? '—' : '${p.defaults.temp}°C';
    final s = p.defaults.spin == 0 ? 'no spin' : '${p.defaults.spin} rpm';
    return '$t · $s';
  }
}

/// Chip di un preferito: tap avvia, long-press elimina.
class _FavoriteChip extends StatelessWidget {
  final FavoriteWash fav;
  const _FavoriteChip(this.fav);

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onLongPress: () async {
        final ok = await showDialog<bool>(
          context: context,
          builder: (_) => AlertDialog(
            title: Text('Eliminare "${fav.customName}"?'),
            actions: [
              TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('Annulla')),
              TextButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('Elimina')),
            ],
          ),
        );
        if (ok == true) {
          await context.read<AppState>().removeFavorite(fav.id);
        }
      },
      child: ActionChip(
        label: Text(fav.customName),
        avatar: const Icon(Icons.star, size: 18, color: Color(0xFFf59e0b)),
        onPressed: () {
          final state = context.findAncestorStateOfType<_StartTabState>();
          state?._startWith(
            programName: fav.programName,
            temp: fav.temp,
            spin: fav.spin,
            soil: fav.soil,
            options: fav.options,
            labelForMsg: fav.customName,
          );
        },
      ),
    );
  }
}

/// Editor del programma selezionato: override + opzioni + azioni.
class _ProgramEditor extends StatelessWidget {
  final ProgramDefinition program;
  final TextEditingController tempCtrl;
  final TextEditingController spinCtrl;
  final TextEditingController soilCtrl;
  final Set<String> options;
  final void Function(String option, bool selected) onOptionToggle;
  final VoidCallback onStart;
  final VoidCallback onSaveFavorite;
  final VoidCallback onClose;

  const _ProgramEditor({
    required this.program,
    required this.tempCtrl,
    required this.spinCtrl,
    required this.soilCtrl,
    required this.options,
    required this.onOptionToggle,
    required this.onStart,
    required this.onSaveFavorite,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(iconFor(program), color: colorFor(program), size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(italianName(program),
                    style: const TextStyle(
                        fontSize: 17, fontWeight: FontWeight.w700)),
              ),
              IconButton(
                icon: const Icon(Icons.close, size: 20),
                onPressed: onClose,
                tooltip: 'Chiudi',
              ),
            ]),
            const SizedBox(height: 8),
            // parametri: tap per modificare (menu di scelta)
            const Row(
              children: [
                Icon(Icons.tune, size: 14, color: Colors.white54),
                SizedBox(width: 4),
                Text('Personalizza',
                    style: TextStyle(fontSize: 11, color: Colors.white54, letterSpacing: 0.5)),
              ],
            ),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(
                  child: _ParamPicker(
                icon: Icons.thermostat,
                label: 'Temp',
                allowed: program.allowed.temp,
                ctrl: tempCtrl,
                fmt: (v) => v == 255 ? '—' : '$v°',
              )),
              const SizedBox(width: 10),
              Expanded(
                  child: _ParamPicker(
                icon: Icons.rotate_right,
                label: 'Centrifuga',
                allowed: program.allowed.spin,
                ctrl: spinCtrl,
                fmt: (v) => v == 0 ? 'no spin' : '$v',
              )),
              const SizedBox(width: 10),
              Expanded(
                  child: _ParamPicker(
                icon: Icons.opacity,
                label: 'Sporco',
                allowed: program.allowed.soil,
                ctrl: soilCtrl,
                fmt: (v) => '$v',
              )),
            ]),
            if (program.allowed.options.isNotEmpty) ...[
              const SizedBox(height: 14),
              const Row(
                children: [
                  Icon(Icons.add_circle_outline, size: 14, color: Colors.white54),
                  SizedBox(width: 4),
                  Text('Opzioni',
                      style: TextStyle(
                          fontSize: 11, color: Colors.white54, letterSpacing: 0.5)),
                ],
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final opt in program.allowed.options)
                    FilterChip(
                      label: Text(kOptionLabels[opt] ?? opt),
                      selected: options.contains(opt),
                      onSelected: (v) => onOptionToggle(opt, v),
                    ),
                ],
              ),
            ],
            const SizedBox(height: 16),
            Row(children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: onStart,
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Avvia'),
                ),
              ),
              const SizedBox(width: 8),
              IconButton.filledTonal(
                onPressed: onSaveFavorite,
                icon: const Icon(Icons.star_border),
                tooltip: 'Salva come preferito',
              ),
            ]),
          ],
        ),
      ),
    );
  }
}

/// Selettore parametro (temperatura/centrifuga/sporco) compatto e chiaro.
/// Mostra il valore come "pill" tapapbile che apre un PopupMenu.
class _ParamPicker extends StatelessWidget {
  final IconData icon;
  final String label;
  final List<int> allowed;
  final TextEditingController ctrl;
  final String Function(int) fmt;

  const _ParamPicker({
    required this.icon,
    required this.label,
    required this.allowed,
    required this.ctrl,
    required this.fmt,
  });

  int get _current => int.tryParse(ctrl.text) ?? allowed.first;

  @override
  Widget build(BuildContext context) {
    final cur = _current;
    final isDefault = cur.toString() == ctrl.text && _isInitialDefault();
    return PopupMenuButton<int>(
      tooltip: 'Cambia $label',
      onSelected: (v) => ctrl.text = v.toString(),
      itemBuilder: (_) => [
        for (final v in allowed)
          PopupMenuItem(
            value: v,
            child: Row(children: [
              if (v == cur)
                const Icon(Icons.check, size: 16, color: Color(0xFF38bdf8))
              else
                const SizedBox(width: 16),
              const SizedBox(width: 8),
              Text(fmt(v)),
            ]),
          ),
      ],
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        decoration: BoxDecoration(
          color: const Color(0xFF0f172a),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: isDefault ? Colors.white12 : const Color(0xFF38bdf8),
            width: isDefault ? 1 : 1.5,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(icon, size: 13, color: Colors.white54),
              const SizedBox(width: 4),
              Text(label.toUpperCase(),
                  style: const TextStyle(fontSize: 9, color: Colors.white54, letterSpacing: 1)),
              const Spacer(),
              const Icon(Icons.arrow_drop_down, size: 16, color: Colors.white38),
            ]),
            const SizedBox(height: 4),
            Text(
              fmt(cur),
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: isDefault ? Colors.white : const Color(0xFF38bdf8),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Heuristica: considera "default" se il valore è il primo ammesso
  /// (esclude così i casi in cui l'utente ha già modificato).
  bool _isInitialDefault() => _current == allowed.first;
}


// ===========================================================================
// TAB IMPOSTAZIONI
// ===========================================================================
class SettingsTab extends StatefulWidget {
  const SettingsTab({super.key});
  @override
  State<SettingsTab> createState() => _SettingsTabState();
}

class _SettingsTabState extends State<SettingsTab> {
  final _ipCtrl = TextEditingController();
  StreamSubscription<Uri>? _linkSub;
  PendingLogin? _pending;
  String _msg = '';
  bool _busy = false;
  // stato scoperta lavatrice
  bool _scanning = false;
  bool _scanCancelled = false;
  int _scanDone = 0;
  int _scanTotal = 254;
  String? _scanSubnet;

  @override
  void initState() {
    super.initState();
    _setupDeepLink();
  }

  void _setupDeepLink() {
    try {
      final links = AppLinks();
      _linkSub = links.uriLinkStream.listen((uri) {
        _handleCallback(uri.toString());
      });
    } catch (_) {
      // deep link non disponibile (es. desktop) — fallback manuale
    }
  }

  Future<void> _handleCallback(String callbackUrl) async {
    if (_pending == null) return;
    setState(() {
      _busy = true;
      _msg = 'Autenticazione…';
    });
    try {
      final idToken = await completeLogin(_pending!, callbackUrl);
      setState(() => _msg = 'Login OK. Importo programmi…');
      final records = await fetchAppliances(idToken);
      final matches = findMatchingWashers(records, 'BWM 149PH7');
      if (matches.isEmpty) {
        setState(() {
          _busy = false;
          _msg = "Nessuna BWM 149PH7 trovata nell'account.";
        });
        return;
      }
      final catalog = normalizeCatalog(matches.first,
          importedAt: DateTime.now().toIso8601String());
      await context.read<AppState>().setCatalog(catalog);
      setState(() {
        _busy = false;
        _msg = '✓ ${catalog.programs.length} programmi importati.';
      });
    } catch (e) {
      setState(() {
        _busy = false;
        _msg = '✗ $e';
      });
    } finally {
      _pending = null;
    }
  }

  Future<void> _startLogin() async {
    setState(() => _busy = true);
    final pending = beginLogin();
    _pending = pending;
    setState(() {
      _busy = false;
      _msg = 'Apri il browser per accedere a Candy.\n'
          'Su desktop: copia l\'URL candy:// qui sotto dopo il login.';
    });
    await launchUrl(Uri.parse(pending.authorizationUrl),
        mode: LaunchMode.externalApplication);
  }

  /// Scopre l'IP della lavatrice scansionando la sottorete locale.
  Future<void> _discoverWasher() async {
    final app = context.read<AppState>();
    setState(() {
      _scanning = true;
      _scanCancelled = false;
      _scanDone = 0;
      _scanTotal = 254;
      _msg = '';
    });
    String subnet;
    try {
      final localIp = await getLocalIp();
      subnet = subnetPrefix(localIp);
    } catch (e) {
      setState(() {
        _scanning = false;
        _msg = '✗ Impossibile determinare la rete: $e';
      });
      return;
    }
    setState(() => _scanSubnet = subnet);

    String? found;
    try {
      found = await scanForCandy(
        subnet: subnet,
        onProgress: (scanned, total) {
          if (!mounted) return;
          setState(() {
            _scanDone = scanned;
            _scanTotal = total;
          });
        },
        cancelFlag: () => _scanCancelled,
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _scanning = false;
        _msg = '✗ Errore durante la scansione: $e';
      });
      return;
    }
    if (!mounted) return;

    if (found != null) {
      // reset chiave vecchia, salva nuovo IP
      await app.setCachedKey(null);
      await app.setCandyIp(found);
      _ipCtrl.text = found;
      setState(() {
        _scanning = false;
        _msg = '✓ Lavatrice trovata su $found';
      });
    } else if (_scanCancelled) {
      setState(() {
        _scanning = false;
        _msg = 'Scansione annullata.';
      });
    } else {
      setState(() {
        _scanning = false;
        _msg = 'Nessuna lavatrice trovata sulla rete $subnet.*';
      });
    }
  }

  @override
  void dispose() {
    _linkSub?.cancel();
    _ipCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    _ipCtrl.text = app.candyIp;
    final catalog = app.catalog;
    return Scaffold(
      appBar: AppBar(title: const Text('Impostazioni')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          sectionTitle('Lavatrice'),
          // --- Scoperta automatica ---
          FilledButton.tonalIcon(
            onPressed: _scanning ? null : _discoverWasher,
            icon: _scanning
                ? const SizedBox(
                    width: 18, height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.search),
            label: Text(_scanning ? 'Scansione…' : 'Cerca lavatrice'),
          ),
          if (_scanning) ...[
            const SizedBox(height: 12),
            LinearProgressIndicator(
              value: _scanTotal > 0 ? _scanDone / _scanTotal : 0,
            ),
            const SizedBox(height: 6),
            Row(children: [
              Expanded(
                child: Text(
                  _scanSubnet != null
                      ? 'Scansione $_scanSubnet.* ($_scanDone/$_scanTotal)…'
                      : 'Avvio scansione…',
                  style: const TextStyle(fontSize: 12, color: Colors.white54),
                ),
              ),
              TextButton(
                onPressed: () => setState(() => _scanCancelled = true),
                child: const Text('Annulla'),
              ),
            ]),
          ],
          const SizedBox(height: 16),
          // --- Inserimento manuale (fallback) ---
          Row(children: [
            Expanded(
              child: TextField(
                controller: _ipCtrl,
                decoration: const InputDecoration(
                    labelText: 'Indirizzo IP', border: OutlineInputBorder()),
              ),
            ),
            const SizedBox(width: 12),
            FilledButton(
              onPressed: () async {
                await app.setCachedKey(null); // reset chiave se cambia IP
                await app.setCandyIp(_ipCtrl.text.trim());
                setState(() => _msg = 'IP salvato.');
              },
              child: const Text('Salva'),
            ),
          ]),
          const SizedBox(height: 8),
          Text('Chiave cache: ${app.cachedKey ?? "(nessuna)"}',
              style: const TextStyle(color: Colors.white54, fontSize: 12)),
          const SizedBox(height: 24),
          sectionTitle('Catalogo programmi'),
          if (catalog != null) ...[
            Text('${catalog.programs.length} programmi '
                '(${catalog.appliance.model} ${catalog.appliance.idMasked})'),
            const SizedBox(height: 4),
            Text('Source: ${catalog.source} • Importato: ${catalog.importedAt}',
                style: const TextStyle(color: Colors.white54, fontSize: 12)),
          ] else
            const Text('Nessun catalogo caricato.'),
          const SizedBox(height: 16),
          sectionTitle('Cloud Candy (login)'),
          FilledButton.icon(
            onPressed: _busy ? null : _startLogin,
            icon: const Icon(Icons.cloud_download),
            label: const Text('Importa programmi dal cloud'),
          ),
          const SizedBox(height: 12),
          if (_pending != null) ...[
            const Text('Incolla qui il callback candy:// dopo il login:'),
            TextField(
              decoration: const InputDecoration(
                  hintText: 'candy://mobilesdk/detect/oauth/done#…',
                  border: OutlineInputBorder()),
              onSubmitted: (v) => _handleCallback(v),
            ),
          ],
          if (_msg.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(_msg,
                  style: const TextStyle(color: Colors.orange, fontSize: 13)),
            ),
        ],
      ),
    );
  }
}
