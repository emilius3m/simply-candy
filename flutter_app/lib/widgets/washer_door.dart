/// Oblò frontale animato della lavatrice (tema "lavatrice reale").
///
/// CustomPainter che disegna:
///   - cornice cromata (anello esterno)
///   - vetro con riflessi e sfumatura
///   - cestello forato che ruota (gira solo se [running])
///   - "acqua" sul fondo se [running]
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Widget dell'oblò che mostra lo stato visivo della lavatrice.
class WasherDoor extends StatefulWidget {
  final bool running;   // true = cestello gira
  final bool online;    // true = dispositivo raggiungibile
  final double size;    // diametro dell'oblò
  final Color waterColor;

  const WasherDoor({
    super.key,
    required this.running,
    required this.online,
    this.size = 220,
    this.waterColor = const Color(0xFF38bdf8),
  });

  @override
  State<WasherDoor> createState() => _WasherDoorState();
}

class _WasherDoorState extends State<WasherDoor>
    with SingleTickerProviderStateMixin {
  late final AnimationController _spin;

  @override
  void initState() {
    super.initState();
    _spin = AnimationController(
      vsync: this,
      // 1 giro ogni ~1.4s, tipico di una lavatrice in lavaggio
      duration: const Duration(milliseconds: 1400),
    );
    _updateSpin();
  }

  @override
  void didUpdateWidget(covariant WasherDoor old) {
    super.didUpdateWidget(old);
    if (old.running != widget.running) {
      _updateSpin();
    }
  }

  void _updateSpin() {
    if (widget.running) {
      _spin.repeat();
    } else {
      _spin.stop();
    }
  }

  @override
  void dispose() {
    _spin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _spin,
      builder: (context, _) {
        return CustomPaint(
          size: Size(widget.size, widget.size),
          painter: _DoorPainter(
            rotation: _spin.value,
            running: widget.running,
            online: widget.online,
            waterColor: widget.waterColor,
          ),
        );
      },
    );
  }
}

class _DoorPainter extends CustomPainter {
  final double rotation; // 0..1
  final bool running;
  final bool online;
  final Color waterColor;

  _DoorPainter({
    required this.rotation,
    required this.running,
    required this.online,
    required this.waterColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;

    // 1) Cornice cromata esterna
    final framePaint = Paint()
      ..shader = RadialGradient(
        colors: [
          Colors.white.withValues(alpha: 0.15),
          const Color(0xFF94a3b8),
          const Color(0xFF475569),
          const Color(0xFF1e293b),
        ],
        stops: const [0.0, 0.85, 0.95, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: radius));
    canvas.drawCircle(center, radius, framePaint);

    // 2) Bordo vetro (anello interno scuro)
    final glassRing = Paint()
      ..color = Colors.black54
      ..style = PaintingStyle.fill;
    canvas.drawCircle(center, radius * 0.86, glassRing);

    // 3) Clip circolare per il contenuto (cestello)
    final glassRect = Rect.fromCircle(center: center, radius: radius * 0.82);
    canvas.save();
    canvas.clipPath(Path()..addOval(glassRect));

    // 3a) Sfondo del cestello (acciaio scuro)
    final drumBg = Paint()
      ..shader = RadialGradient(
        colors: const [Color(0xFF334155), Color(0xFF0f172a)],
        center: Alignment.center,
      ).createShader(glassRect);
    canvas.drawRect(glassRect, drumBg);

    // 3b) Cestello forato rotante
    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(rotation * 2 * math.pi);
    final drumRadius = radius * 0.78;
    _drawDrum(canvas, drumRadius);
    canvas.restore();

    // 3c) Acqua sul fondo se in funzione
    if (running) {
      _drawWater(canvas, glassRect);
    }

    // 3d) Riflesso sul vetro (mezzaluna in alto a sinistra)
    final glassReflect = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          Colors.white.withValues(alpha: 0.35),
          Colors.white.withValues(alpha: 0.0),
        ],
        stops: const [0.0, 0.4],
      ).createShader(glassRect);
    canvas.drawRect(glassRect, glassReflect);

    // 3e) Soffio luminoso curvo in alto (riflesso secondario)
    final arcPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.25)
      ..style = PaintingStyle.stroke
      ..strokeWidth = radius * 0.06
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius * 0.66),
      -math.pi * 0.85,
      math.pi * 0.5,
      false,
      arcPaint,
    );

    canvas.restore();

    // 4) Maniglia dell'oblò (piccola sporgenza a destra)
    final handlePaint = Paint()
      ..color = const Color(0xFF64748b)
      ..style = PaintingStyle.fill;
    final handleRect = Rect.fromCenter(
      center: Offset(center.dx + radius * 0.92, center.dy),
      width: radius * 0.18,
      height: radius * 0.12,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(handleRect, Radius.circular(radius * 0.06)),
      handlePaint,
    );
  }

  void _drawDrum(Canvas canvas, double r) {
    // fori del cestello disposti a spirale/cerchi concentrici
    final holePaint = Paint()..color = Colors.black.withValues(alpha: 0.45);
    final rings = [0.35, 0.55, 0.75, 0.92];
    final counts = [6, 10, 14, 18];
    for (var i = 0; i < rings.length; i++) {
      final rr = r * rings[i];
      final n = counts[i];
      for (var j = 0; j < n; j++) {
        final a = (j / n) * 2 * math.pi + i * 0.3;
        final p = Offset(math.cos(a) * rr, math.sin(a) * rr);
        canvas.drawCircle(p, r * 0.035, holePaint);
      }
    }
    // asse centrale + bracci
    final armPaint = Paint()
      ..color = const Color(0xFF475569)
      ..style = PaintingStyle.stroke
      ..strokeWidth = r * 0.06;
    for (var i = 0; i < 3; i++) {
      final a = (i / 3) * 2 * math.pi;
      canvas.drawLine(
        Offset.zero,
        Offset(math.cos(a) * r * 0.7, math.sin(a) * r * 0.7),
        armPaint,
      );
    }
    canvas.drawCircle(Offset.zero, r * 0.12, Paint()..color = const Color(0xFF334155));
  }

  void _drawWater(Canvas canvas, Rect rect) {
    // livello acqua a circa il 35% dal basso, con lieve ondulazione
    final level = rect.bottom - rect.height * 0.35;
    final wavePaint = Paint()
      ..shader = LinearGradient(
        colors: [waterColor.withValues(alpha: 0.55), waterColor.withValues(alpha: 0.25)],
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
      ).createShader(Rect.fromLTRB(rect.left, level, rect.right, rect.bottom));
    final path = Path();
    path.moveTo(rect.left, level);
    // onda sinusoidale
    const steps = 24;
    for (var i = 0; i <= steps; i++) {
      final x = rect.left + (rect.width * i / steps);
      final y = level + math.sin((i / steps) * 2 * math.pi * 2) * 4;
      path.lineTo(x, y);
    }
    path.lineTo(rect.right, rect.bottom);
    path.lineTo(rect.left, rect.bottom);
    path.close();
    canvas.drawPath(path, wavePaint);
  }

  @override
  bool shouldRepaint(covariant _DoorPainter old) =>
      old.rotation != rotation ||
      old.running != running ||
      old.online != online ||
      old.waterColor != waterColor;
}
