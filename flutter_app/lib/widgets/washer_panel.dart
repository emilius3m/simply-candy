/// Pannello frontale completo della lavatrice (corpo + oblò + consolle).
///
/// Disegna una lavatrice realistica con:
///   - Corpo in acciaio con bordi arrotondati e riflessi
///   - Cassetto del detersivo in alto
///   - Consolle di comando con spie LED e stato/fase
///   - Oblò centrale con cestello rotante, acqua, vetro e riflessi
///   - Display LCD tempo residuo sovrapposto all'oblò
///   - Spie parametri sotto l'oblò (temp, centrifuga, programma)
///   - Badge Candy
///   - Zoccolo con piedini
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Pannello lavatrice realistico per la schermata Stato.
class WasherPanel extends StatefulWidget {
  /// True = cestello gira (lavatrice in funzione).
  final bool running;

  /// True = dispositivo raggiungibile via rete.
  final bool online;

  /// Etichetta dello stato macchina (es. "In funzione", "Inattiva").
  final String? statusLabel;

  /// Etichetta della fase corrente (es. "Lavaggio", "Centrifuga").
  final String? phaseLabel;

  /// Tempo residuo formattato (es. "1:28").
  final String? remainingTime;

  /// Temperatura corrente (es. "40").
  final String? temp;

  /// Centrifuga corrente (es. "14" = x100 rpm).
  final String? spinSp;

  /// Numero programma in esecuzione.
  final String? programNumber;

  /// Nome italiano del programma (es. "Cotone Resistente").
  final String? programName;

  /// True se c'è un errore attivo.
  final bool hasError;

  /// Larghezza massima del pannello.
  final double maxWidth;

  const WasherPanel({
    super.key,
    required this.running,
    required this.online,
    this.statusLabel,
    this.phaseLabel,
    this.remainingTime,
    this.temp,
    this.spinSp,
    this.programNumber,
    this.programName,
    this.hasError = false,
    this.maxWidth = 360,
  });

  @override
  State<WasherPanel> createState() => _WasherPanelState();
}

class _WasherPanelState extends State<WasherPanel>
    with TickerProviderStateMixin {
  late final AnimationController _drum;
  late final AnimationController _wave;

  @override
  void initState() {
    super.initState();
    _drum = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    );
    _wave = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    )..repeat();
    _updateDrum();
  }

  @override
  void didUpdateWidget(covariant WasherPanel old) {
    super.didUpdateWidget(old);
    if (old.running != widget.running) {
      _updateDrum();
    }
  }

  void _updateDrum() {
    if (widget.running) {
      _drum.repeat();
    } else {
      _drum.stop();
    }
  }

  @override
  void dispose() {
    _drum.dispose();
    _wave.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final screenW = MediaQuery.of(context).size.width - 32;
    final w = math.min(widget.maxWidth, screenW);
    final h = w * 1.38;

    return Center(
      child: AnimatedBuilder(
        animation: Listenable.merge([_drum, _wave]),
        builder: (context, _) {
          return CustomPaint(
            size: Size(w, h),
            painter: _WasherBodyPainter(
              running: widget.running,
              online: widget.online,
              statusLabel: widget.statusLabel,
              phaseLabel: widget.phaseLabel,
              remainingTime: widget.remainingTime,
              temp: widget.temp,
              spinSp: widget.spinSp,
              programNumber: widget.programNumber,
              programName: widget.programName,
              hasError: widget.hasError,
              drumRotation: _drum.value,
              wavePhase: _wave.value,
            ),
          );
        },
      ),
    );
  }
}

class _WasherBodyPainter extends CustomPainter {
  final bool running;
  final bool online;
  final String? statusLabel;
  final String? phaseLabel;
  final String? remainingTime;
  final String? temp;
  final String? spinSp;
  final String? programNumber;
  final String? programName;
  final bool hasError;
  final double drumRotation;
  final double wavePhase;

  _WasherBodyPainter({
    required this.running,
    required this.online,
    required this.statusLabel,
    required this.phaseLabel,
    required this.remainingTime,
    required this.temp,
    required this.spinSp,
    required this.programNumber,
    required this.programName,
    required this.hasError,
    required this.drumRotation,
    required this.wavePhase,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;

    _drawBody(canvas, w, h);
    _drawConsole(canvas, w, h);
    _drawDoor(canvas, w, h);
    _drawGauges(canvas, w, h);
    _drawBase(canvas, w, h);
  }

  // === CORPO IN ACCIAIO ===
  void _drawBody(Canvas canvas, double w, double h) {
    final bodyRect = RRect.fromRectAndCorners(
      Rect.fromLTWH(0, 0, w, h),
      topLeft: const Radius.circular(14),
      topRight: const Radius.circular(14),
      bottomLeft: const Radius.circular(6),
      bottomRight: const Radius.circular(6),
    );

    // Gradiente acciaio
    final bodyPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: const [
          Color(0xFF3a4557),
          Color(0xFF2a3444),
          Color(0xFF1e2836),
          Color(0xFF232f3e),
          Color(0xFF2a3444),
        ],
        stops: const [0.0, 0.25, 0.5, 0.75, 1.0],
      ).createShader(Rect.fromLTWH(0, 0, w, h));
    canvas.drawRRect(bodyRect, bodyPaint);

    // Bordo lamiera
    canvas.drawRRect(
      bodyRect,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Colors.white.withValues(alpha: 0.12),
            Colors.white.withValues(alpha: 0.03),
          ],
        ).createShader(Rect.fromLTWH(0, 0, w, h)),
    );

    // Striscia luce in alto
    canvas.drawRect(
      Rect.fromLTWH(6, 2, w - 12, h * 0.06),
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Colors.white.withValues(alpha: 0.07),
            Colors.white.withValues(alpha: 0.0),
          ],
        ).createShader(Rect.fromLTWH(0, 0, w, h * 0.06)),
    );
  }

  // === CONSOLLE SUPERIORE ===
  void _drawConsole(Canvas canvas, double w, double h) {
    final consoleTop = h * 0.03;
    final consoleH = h * 0.18;

    // Sfondo consolle
    canvas.drawRect(
      Rect.fromLTWH(8, consoleTop, w - 16, consoleH),
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: const [Color(0xFF1a2332), Color(0xFF151d2a)],
        ).createShader(Rect.fromLTWH(0, consoleTop, w, consoleH)),
    );

    // Linea separazione
    canvas.drawLine(
      Offset(12, consoleTop + consoleH),
      Offset(w - 12, consoleTop + consoleH),
      Paint()
        ..color = Colors.white.withValues(alpha: 0.06)
        ..strokeWidth = 1,
    );

    // Cassetto detersivo
    final drawerW = w * 0.20;
    final drawerH = consoleH * 0.32;
    final drawerLeft = w * 0.07;
    final drawerTop = consoleTop + consoleH * 0.15;
    final drawerRect = RRect.fromRectAndRadius(
      Rect.fromLTWH(drawerLeft, drawerTop, drawerW, drawerH),
      const Radius.circular(3),
    );
    canvas.drawRRect(drawerRect, Paint()..color = const Color(0xFF2a3444));
    canvas.drawRRect(
      drawerRect,
      Paint()
        ..style = PaintingStyle.stroke
        ..color = Colors.white.withValues(alpha: 0.08)
        ..strokeWidth = 0.8,
    );
    // Maniglietta cassetto
    canvas.drawLine(
      Offset(drawerLeft + drawerW * 0.3, drawerTop + drawerH - 3),
      Offset(drawerLeft + drawerW * 0.7, drawerTop + drawerH - 3),
      Paint()
        ..color = Colors.white.withValues(alpha: 0.15)
        ..strokeWidth = 1.5
        ..strokeCap = StrokeCap.round,
    );

    // Badge "Candy"
    final brandPainter = TextPainter(
      text: const TextSpan(
        text: 'Candy',
        style: TextStyle(
          color: Color(0xFF5a6a7a),
          fontSize: 14,
          fontWeight: FontWeight.w700,
          fontStyle: FontStyle.italic,
          letterSpacing: 1.5,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    brandPainter.paint(
      canvas,
      Offset(w - brandPainter.width - w * 0.07, consoleTop + consoleH * 0.18),
    );

    // === Spie LED consolle ===
    final ledY = consoleTop + consoleH * 0.60;
    final ledStartX = w * 0.07;

    // LED 1: Online (verde se online, rosso se offline)
    _drawLed(
      canvas,
      Offset(ledStartX, ledY),
      online ? const Color(0xFF22c55e) : const Color(0xFFef4444),
      online ? 0.7 : 0.4,
    );

    // LED 2: Running (arancio se in funzione)
    _drawLed(
      canvas,
      Offset(ledStartX + 20, ledY),
      const Color(0xFFf59e0b),
      running ? 0.8 : 0.1,
    );

    // LED 3: Errore (rosso se errore)
    _drawLed(
      canvas,
      Offset(ledStartX + 40, ledY),
      const Color(0xFFef4444),
      hasError ? 0.9 : 0.1,
    );

    // Testo stato + fase nella consolle
    final hasStatus = statusLabel != null || phaseLabel != null;
    if (hasStatus) {
      final statusText = [
        ?statusLabel,
        ?phaseLabel,
      ].join(' · ');

      final statusColor = running
          ? const Color(0xFF38bdf8)
          : online
              ? const Color(0xFF94a3b8)
              : const Color(0xFF475569);

      final statusPainter = TextPainter(
        text: TextSpan(
          text: statusText,
          style: TextStyle(
            color: statusColor,
            fontSize: 11,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.5,
          ),
        ),
        textDirection: TextDirection.ltr,
        maxLines: 1,
        ellipsis: '…',
      )..layout(maxWidth: w * 0.55);
      statusPainter.paint(
        canvas,
        Offset(ledStartX + 58, ledY - statusPainter.height / 2),
      );
    } else if (!online) {
      final offPainter = TextPainter(
        text: const TextSpan(
          text: '— non connesso —',
          style: TextStyle(
            color: Color(0xFF475569),
            fontSize: 10,
            letterSpacing: 0.5,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      offPainter.paint(
        canvas,
        Offset(ledStartX + 58, ledY - offPainter.height / 2),
      );
    }

    // Etichette LED
    final ledLabelsY = ledY + 10;
    for (final entry in [
      (x: ledStartX, text: 'PWR'),
      (x: ledStartX + 20, text: 'RUN'),
      (x: ledStartX + 40, text: 'ERR'),
    ]) {
      final lp = TextPainter(
        text: TextSpan(
          text: entry.text,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.2),
            fontSize: 6,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.5,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      lp.paint(canvas, Offset(entry.x - lp.width / 2, ledLabelsY));
    }
  }

  // === OBLÒ CON CESTELLO E ACQUA ===
  void _drawDoor(Canvas canvas, double w, double h) {
    final doorCenterX = w / 2;
    final doorCenterY = h * 0.58;       // abbassato per staccarlo dai gauge
    final doorRadius = w * 0.26;        // raggio ridotto per fare spazio
    final center = Offset(doorCenterX, doorCenterY);

    // Ombra esterna
    canvas.drawCircle(
      Offset(center.dx + 2, center.dy + 3),
      doorRadius + 8,
      Paint()
        ..color = Colors.black.withValues(alpha: 0.35)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10),
    );

    // Anello cromato esterno
    canvas.drawCircle(
      center,
      doorRadius + 5,
      Paint()
        ..shader = RadialGradient(
          colors: [
            Colors.white.withValues(alpha: 0.18),
            const Color(0xFF8899aa),
            const Color(0xFF5a6a7a),
            const Color(0xFF3a4557),
            const Color(0xFF2a3444),
          ],
          stops: const [0.0, 0.7, 0.85, 0.95, 1.0],
        ).createShader(
            Rect.fromCircle(center: center, radius: doorRadius + 5)),
    );

    // Guarnizione
    canvas.drawCircle(
      center,
      doorRadius,
      Paint()..color = const Color(0xFF1a1a2a),
    );

    // Area vetro clippata
    final glassRadius = doorRadius * 0.88;
    final glassRect = Rect.fromCircle(center: center, radius: glassRadius);
    canvas.save();
    canvas.clipPath(Path()..addOval(glassRect));

    // Sfondo cestello
    canvas.drawRect(
      glassRect,
      Paint()
        ..shader = RadialGradient(
          colors: const [Color(0xFF2a3444), Color(0xFF0c1220)],
        ).createShader(glassRect),
    );

    // Cestello rotante
    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(drumRotation * 2 * math.pi);
    _drawDrum(canvas, glassRadius * 0.95);
    canvas.restore();

    // Acqua sul fondo se in funzione
    if (running) {
      _drawWater(canvas, glassRect);
    }

    // Riflesso vetro
    canvas.drawRect(
      glassRect,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Colors.white.withValues(alpha: 0.22),
            Colors.white.withValues(alpha: 0.0),
          ],
          stops: const [0.0, 0.45],
        ).createShader(glassRect),
    );

    // Arco riflesso secondario
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: glassRadius * 0.75),
      -math.pi * 0.85,
      math.pi * 0.45,
      false,
      Paint()
        ..color = Colors.white.withValues(alpha: 0.20)
        ..style = PaintingStyle.stroke
        ..strokeWidth = glassRadius * 0.05
        ..strokeCap = StrokeCap.round,
    );

    canvas.restore();

    // === DISPLAY LCD SOVRAPPOSTO ALL'OBLÒ ===
    if (remainingTime != null) {
      _drawLcdOverlay(canvas, center, doorRadius);
    }

    // Maniglia oblò
    final handleCenter = Offset(center.dx + doorRadius + 3, center.dy);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromCenter(
          center: handleCenter,
          width: doorRadius * 0.14,
          height: doorRadius * 0.42,
        ),
        Radius.circular(doorRadius * 0.07),
      ),
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: const [Color(0xFF7a8a9a), Color(0xFF4a5a6a)],
        ).createShader(Rect.fromCenter(
          center: handleCenter,
          width: doorRadius * 0.14,
          height: doorRadius * 0.42,
        )),
    );
    // Riflesso maniglia
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromCenter(
          center: Offset(handleCenter.dx - 1, handleCenter.dy - doorRadius * 0.08),
          width: doorRadius * 0.04,
          height: doorRadius * 0.15,
        ),
        Radius.circular(doorRadius * 0.02),
      ),
      Paint()..color = Colors.white.withValues(alpha: 0.2),
    );
  }

  void _drawLcdOverlay(Canvas canvas, Offset center, double doorRadius) {
    // Sfondo LCD
    final lcdW = doorRadius * 1.1;
    final lcdH = doorRadius * 0.55;
    final lcdRect = RRect.fromRectAndRadius(
      Rect.fromCenter(center: center, width: lcdW, height: lcdH),
      const Radius.circular(8),
    );
    canvas.drawRRect(
      lcdRect,
      Paint()..color = const Color(0xE0051a10),
    );
    canvas.drawRRect(
      lcdRect,
      Paint()
        ..style = PaintingStyle.stroke
        ..color = Colors.black87
        ..strokeWidth = 2,
    );

    // Etichetta "TEMPO"
    final labelPainter = TextPainter(
      text: const TextSpan(
        text: 'TEMPO',
        style: TextStyle(
          fontSize: 8,
          color: Color(0xFF1f6b4a),
          letterSpacing: 2,
          fontWeight: FontWeight.w700,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    labelPainter.paint(
      canvas,
      Offset(center.dx - labelPainter.width / 2, center.dy - lcdH * 0.35),
    );

    // Cifre tempo
    const digitColor = Color(0xFF34d399);
    final timePainter = TextPainter(
      text: TextSpan(
        text: remainingTime!,
        style: const TextStyle(
          fontFamily: 'monospace',
          fontSize: 28,
          fontWeight: FontWeight.w700,
          color: digitColor,
          letterSpacing: 2,
          shadows: [
            Shadow(color: Color(0x9934d399), blurRadius: 12),
          ],
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    timePainter.paint(
      canvas,
      Offset(center.dx - timePainter.width / 2, center.dy - timePainter.height / 2 + 4),
    );

    // Indicatore errore
    if (hasError) {
      final errPainter = TextPainter(
        text: const TextSpan(
          text: '⚠ Errore',
          style: TextStyle(color: Color(0xFFef4444), fontSize: 9),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      errPainter.paint(
        canvas,
        Offset(center.dx - errPainter.width / 2, center.dy + lcdH * 0.25),
      );
    }
  }

  void _drawDrum(Canvas canvas, double r) {
    final holePaint = Paint()..color = Colors.black.withValues(alpha: 0.4);
    final rings = [0.3, 0.5, 0.7, 0.88];
    final counts = [5, 8, 12, 16];
    for (var i = 0; i < rings.length; i++) {
      final rr = r * rings[i];
      final n = counts[i];
      for (var j = 0; j < n; j++) {
        final a = (j / n) * 2 * math.pi + i * 0.4;
        final p = Offset(math.cos(a) * rr, math.sin(a) * rr);
        canvas.drawCircle(p, r * 0.028, holePaint);
      }
    }
    // Bracci
    final armPaint = Paint()
      ..color = const Color(0xFF3a4a5a)
      ..style = PaintingStyle.stroke
      ..strokeWidth = r * 0.05;
    for (var i = 0; i < 3; i++) {
      final a = (i / 3) * 2 * math.pi;
      canvas.drawLine(
        Offset.zero,
        Offset(math.cos(a) * r * 0.6, math.sin(a) * r * 0.6),
        armPaint,
      );
    }
    // Mozzo
    canvas.drawCircle(Offset.zero, r * 0.1, Paint()..color = const Color(0xFF2a3a4a));
    canvas.drawCircle(
      Offset.zero,
      r * 0.1,
      Paint()
        ..style = PaintingStyle.stroke
        ..color = Colors.white.withValues(alpha: 0.08)
        ..strokeWidth = 0.5,
    );
  }

  void _drawWater(Canvas canvas, Rect rect) {
    final level = rect.bottom - rect.height * 0.35;
    const waterColor = Color(0xFF38bdf8);
    final wavePaint = Paint()
      ..shader = LinearGradient(
        colors: [
          waterColor.withValues(alpha: 0.55),
          waterColor.withValues(alpha: 0.25),
        ],
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
      ).createShader(Rect.fromLTRB(rect.left, level, rect.right, rect.bottom));

    final path = Path();
    path.moveTo(rect.left, level);
    const steps = 24;
    for (var i = 0; i <= steps; i++) {
      final x = rect.left + (rect.width * i / steps);
      final phase = wavePhase * 2 * math.pi;
      final y = level + math.sin((i / steps) * 2 * math.pi * 2 + phase) * 5;
      path.lineTo(x, y);
    }
    path.lineTo(rect.right, rect.bottom);
    path.lineTo(rect.left, rect.bottom);
    path.close();
    canvas.drawPath(path, wavePaint);
  }

  // === SPIE PARAMETRI SOTTO L'OBLÒ ===
  void _drawGauges(Canvas canvas, double w, double h) {
    // --- Etichetta PROGRAMMA CORRENTE (fascia sopra l'oblò) ---
    _drawCurrentProgram(canvas, w, h);

    // --- Striscia parametri TEMP + SPIN (sotto il programma, sopra l'oblò) ---
    final stripTop = h * 0.295;
    final stripBottom = h * 0.365;
    final stripLeft = w * 0.14;
    final stripRight = w * 0.86;
    final centerY = (stripTop + stripBottom) / 2;

    // sfondo della striscia (pannello strumenti incassato)
    final stripRect = RRect.fromRectAndRadius(
      Rect.fromLTRB(stripLeft, stripTop, stripRight, stripBottom),
      const Radius.circular(8),
    );
    canvas.drawRRect(stripRect, Paint()..color = const Color(0xFF0b1320));
    canvas.drawRRect(
      stripRect,
      Paint()
        ..color = Colors.white.withValues(alpha: 0.05)
        ..style = PaintingStyle.stroke,
    );

    // separatore verticale tra le due spie
    final midX = (stripLeft + stripRight) / 2;
    canvas.drawLine(
      Offset(midX, stripTop + 6),
      Offset(midX, stripBottom - 6),
      Paint()
        ..color = Colors.white.withValues(alpha: 0.06)
        ..strokeWidth = 1,
    );

    // Temperatura (sinistra)
    final tempVal = (temp == null || temp == '255') ? '—' : '$temp°';
    final tempOn = running && temp != '0' && temp != '255';
    _drawGaugeItem(canvas, Offset((stripLeft + midX) / 2, centerY),
        'TEMP', tempVal, tempOn);

    // Centrifuga (destra)
    final spinVal = (spinSp == null || spinSp == '0') ? 'off' : '${spinSp}00';
    final spinOn = phaseLabel == 'Centrifuga';
    _drawGaugeItem(canvas, Offset((midX + stripRight) / 2, centerY),
        'SPIN', spinVal, spinOn);
  }

  /// Disegna il nome del programma corrente in una fascia dedicata (0.22-0.29).
  void _drawCurrentProgram(Canvas canvas, double w, double h) {
    final y = h * 0.245;
    final label = (programName?.isNotEmpty ?? false)
        ? programName!
        : (programNumber != null ? 'Programma $programNumber' : '—');

    // piccola etichetta "PROGRAMMA"
    final cap = TextPainter(
      text: const TextSpan(
        text: 'PROGRAMMA',
        style: TextStyle(
          fontSize: 8,
          color: Color(0xFF64748b),
          letterSpacing: 1.5,
          fontWeight: FontWeight.w700,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    cap.paint(canvas, Offset(w / 2 - cap.width / 2, y - 14));

    // nome programma
    final progColor = running
        ? const Color(0xFF38bdf8)
        : online
            ? const Color(0xFFcbd5e1)
            : const Color(0xFF475569);
    final name = TextPainter(
      text: TextSpan(
        text: label,
        style: TextStyle(
          color: progColor,
          fontSize: 14,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.3,
        ),
      ),
      textDirection: TextDirection.ltr,
      maxLines: 1,
      ellipsis: '…',
    )..layout(maxWidth: w * 0.72);
    name.paint(canvas, Offset(w / 2 - name.width / 2, y + 2));
  }

  void _drawGaugeItem(
    Canvas canvas,
    Offset center,
    String label,
    String value,
    bool on,
  ) {
    final color = on ? const Color(0xFF38bdf8) : const Color(0xFF475569);

    // Etichetta in alto
    final labelPainter = TextPainter(
      text: TextSpan(
        text: label,
        style: TextStyle(
          fontSize: 9,
          color: Colors.white.withValues(alpha: 0.35),
          letterSpacing: 1.2,
          fontWeight: FontWeight.w600,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    labelPainter.paint(
      canvas,
      Offset(center.dx - labelPainter.width / 2, center.dy - 14),
    );

    // Valore in basso
    final valPainter = TextPainter(
      text: TextSpan(
        text: value,
        style: TextStyle(
          color: on ? color : Colors.white54,
          fontSize: 16,
          fontWeight: FontWeight.w700,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    valPainter.paint(
      canvas,
      Offset(center.dx - valPainter.width / 2, center.dy + 1),
    );
  }

  // === ZOCCOLO INFERIORE ===
  void _drawBase(Canvas canvas, double w, double h) {
    final baseTop = h * 0.88;
    canvas.drawRect(
      Rect.fromLTWH(4, baseTop, w - 8, h * 0.10),
      Paint()..color = const Color(0xFF151d2a),
    );
    canvas.drawLine(
      Offset(4, baseTop),
      Offset(w - 4, baseTop),
      Paint()
        ..color = Colors.white.withValues(alpha: 0.05)
        ..strokeWidth = 0.8,
    );
    // Piedini
    final footPaint = Paint()..color = const Color(0xFF0a0f18);
    final footY = h - 3;
    canvas.drawOval(
      Rect.fromCenter(center: Offset(w * 0.2, footY), width: 20, height: 6),
      footPaint,
    );
    canvas.drawOval(
      Rect.fromCenter(center: Offset(w * 0.8, footY), width: 20, height: 6),
      footPaint,
    );
  }

  // === LED HELPER ===
  void _drawLed(Canvas canvas, Offset pos, Color color, double intensity) {
    if (intensity > 0.15) {
      canvas.drawCircle(
        pos,
        6,
        Paint()
          ..color = color.withValues(alpha: 0.3 * intensity)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4),
      );
    }
    canvas.drawCircle(
      pos,
      3,
      Paint()..color = color.withValues(alpha: 0.2 + 0.8 * intensity),
    );
    canvas.drawCircle(
      Offset(pos.dx - 0.5, pos.dy - 0.5),
      1,
      Paint()..color = Colors.white.withValues(alpha: 0.3 * intensity),
    );
  }

  @override
  bool shouldRepaint(covariant _WasherBodyPainter old) =>
      old.running != running ||
      old.online != online ||
      old.statusLabel != statusLabel ||
      old.phaseLabel != phaseLabel ||
      old.remainingTime != remainingTime ||
      old.temp != temp ||
      old.spinSp != spinSp ||
      old.programNumber != programNumber ||
      old.programName != programName ||
      old.hasError != hasError ||
      old.drumRotation != drumRotation ||
      old.wavePhase != wavePhase;
}
