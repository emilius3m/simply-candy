/// Display LCD stile elettrodomestico per il tempo residuo.
///
/// Sfondo scuro verde/nero, cifre monospace luminose, etichetta minuscola.
library;

import 'package:flutter/material.dart';

class LcdDisplay extends StatelessWidget {
  final String value;       // es. "0:28"
  final String label;       // es. "TEMPO RESIDUO"
  final Color digitColor;

  const LcdDisplay({
    super.key,
    required this.value,
    required this.label,
    this.digitColor = const Color(0xFF34d399),
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF051a10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.black87, width: 2),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.5),
            blurRadius: 8,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 9,
              color: Color(0xFF1f6b4a),
              letterSpacing: 2,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: TextStyle(
              fontFamily: 'monospace',
              fontSize: 34,
              fontWeight: FontWeight.w700,
              color: digitColor,
              letterSpacing: 2,
              shadows: [
                Shadow(
                  color: digitColor.withValues(alpha: 0.6),
                  blurRadius: 12,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
