/// Mappatura nomi cloud -> etichette italiane e icone, + programma vs servizio.
///
/// I nomi italiani sono estratti da strings.xml dell'APK decompilato (values-it).
library;

import 'package:flutter/material.dart';

import 'programs.dart';

/// Mappa dal `prstr` cloud all'etichetta italiana leggibile.
const Map<String, String> kItalianNames = {
  'DUAL_WM_WD_OFF': 'Off',
  'DUAL_WM_WD_PROGRAM_NAME_RESISTANT_COTTONS': 'Cotone Resistente',
  'DUAL_WM_WD_PROGRAM_NAME_RESISTANT_ECO_COTTONS': 'Cotone Eco',
  'DUAL_WM_WD_PROGRAM_NAME_SYNTHETIC_AND_COLOURED': 'Sintetici e Colorati',
  'DUAL_WM_WD_PROGRAM_NAME_WOOL': 'Lana',
  'DUAL_WM_WD_PROGRAM_NAME_DELICATES': 'Delicati',
  'DUAL_WM_WD_PROGRAM_NAME_PERFECT_20': 'Perfetto 20°',
  'DUAL_WM_WD_PROGRAM_NAME_RINSE': 'Risciacqui',
  'DUAL_WM_WD_PROGRAM_NAME_DRAIN_SPIN': 'Scarico e Centrifuga',
  'DUAL_WM_WD_PROGRAM_NAME_TUMBLING': 'Refresh Touch',
  'DUAL_WM_WD_PROGRAM_NAME_MAINTENANCE': 'Manutenzione',
  'DUAL_WM_WD_PROGRAM_NAME_PERFECT_RAPID_59': 'Perfect Rapid 59 Min',
  'DUAL_WM_WD_PROGRAM_NAME_RAPID_14_MIN': 'Rapido 14 Min.',
  'DUAL_WM_WD_PROGRAM_NAME_RAPID_30_MIN': 'Rapido 30 Min.',
  'DUAL_WM_WD_PROGRAM_NAME_RAPID_44_MIN': 'Rapido 44 Min.',
  'DUAL_WM_WD_PROGRAM_NAME_HYGIENE_60': 'Igiene 60°',
  'DUAL_WM_WD_PROGRAM_NAME_BABY_60': 'Baby 60°C',
  'DUAL_WM_WD_PROGRAM_NAME_JEANS': 'Jeans',
  'DUAL_WM_WD_PROGRAM_NAME_INTENSIVE_40': 'Intensivo 40°',
};

/// prstr considerati programmi di "servizio" (non lavaggio) da nascondere
/// dalla lista principale. L'utente può comunque crearne un preferito se vuole.
const Set<String> kServicePrograms = {
  'DUAL_WM_WD_OFF',
  'DUAL_WM_WD_PROGRAM_NAME_MAINTENANCE',
};

/// Etichetta italiana di un programma (fallback al prstr se non mappato).
String italianName(ProgramDefinition p) =>
    kItalianNames[p.prstr] ?? p.prstr;

/// Categoria visuale del programma (per icona + colore).
enum ProgramCategory {
  cotone,      // cotoni
  rapido,      // rapid/perfect rapid
  delicato,    // lana, delicati, perfetto 20
  servizio,    // risciacquo, scarico, refresh, manutenzione
  speciale,    // hygiene, baby, jeans, intensivo, sintetici
}

/// Mappa prstr -> categoria.
ProgramCategory categoryOf(ProgramDefinition p) {
  final s = p.prstr;
  if (kServicePrograms.contains(s)) return ProgramCategory.servizio;
  if (s.contains('COTTONS') || s.contains('COTTON')) return ProgramCategory.cotone;
  if (s.contains('RAPID') || s.contains('PERFECT_RAPID')) return ProgramCategory.rapido;
  if (s.contains('WOOL') || s.contains('DELICATES') || s.contains('PERFECT_20')) {
    return ProgramCategory.delicato;
  }
  return ProgramCategory.speciale;
}

/// Icona Material per la categoria.
IconData iconFor(ProgramDefinition p) {
  switch (categoryOf(p)) {
    case ProgramCategory.cotone:
      return Icons.grain; // fibra/tessuto
    case ProgramCategory.rapido:
      return Icons.bolt;
    case ProgramCategory.delicato:
      return Icons.spa;
    case ProgramCategory.servizio:
      return Icons.build;
    case ProgramCategory.speciale:
      return Icons.local_laundry_service;
  }
}

/// Colore d'accento per la categoria.
Color colorFor(ProgramDefinition p) {
  switch (categoryOf(p)) {
    case ProgramCategory.cotone:
      return const Color(0xFF38bdf8); // azzurro
    case ProgramCategory.rapido:
      return const Color(0xFFf59e0b); // ambra
    case ProgramCategory.delicato:
      return const Color(0xFFa78bfa); // viola
    case ProgramCategory.servizio:
      return const Color(0xFF94a3b8); // grigio
    case ProgramCategory.speciale:
      return const Color(0xFF34d399); // verde
  }
}

/// True se il programma è un lavaggio "reale" (da mostrare in lista principale).
bool isWashProgram(ProgramDefinition p) =>
    !kServicePrograms.contains(p.prstr);
