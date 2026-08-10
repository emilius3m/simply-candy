// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'programs.dart';

// ***************************************************************************
// JsonSerializableGenerator
// ***************************************************************************

ProgramDefaults _$ProgramDefaultsFromJson(Map<String, dynamic> json) =>
    ProgramDefaults(
      temp: (json['temp'] as num).toInt(),
      spin: (json['spin'] as num).toInt(),
      soil: (json['soil'] as num).toInt(),
      steam: (json['steam'] as num).toInt(),
      dry: (json['dry'] as num).toInt(),
    );

Map<String, dynamic> _$ProgramDefaultsToJson(ProgramDefaults instance) =>
    <String, dynamic>{
      'temp': instance.temp,
      'spin': instance.spin,
      'soil': instance.soil,
      'steam': instance.steam,
      'dry': instance.dry,
    };

ProgramAllowed _$ProgramAllowedFromJson(Map<String, dynamic> json) =>
    ProgramAllowed(
      temp: (json['temp'] as List<dynamic>).map((e) => (e as num).toInt()).toList(),
      spin: (json['spin'] as List<dynamic>).map((e) => (e as num).toInt()).toList(),
      soil: (json['soil'] as List<dynamic>).map((e) => (e as num).toInt()).toList(),
      options: (json['options'] as List<dynamic>).map((e) => e as String).toList(),
    );

Map<String, dynamic> _$ProgramAllowedToJson(ProgramAllowed instance) =>
    <String, dynamic>{
      'temp': instance.temp,
      'spin': instance.spin,
      'soil': instance.soil,
      'options': instance.options,
    };

ProgramDefinition _$ProgramDefinitionFromJson(Map<String, dynamic> json) =>
    ProgramDefinition(
      name: json['name'] as String,
      prnm: (json['prnm'] as num).toInt(),
      prcode: (json['prcode'] as num).toInt(),
      prstr: json['prstr'] as String,
      defaults:
          ProgramDefaults.fromJson(json['defaults'] as Map<String, dynamic>),
      allowed:
          ProgramAllowed.fromJson(json['allowed'] as Map<String, dynamic>),
      source: json['source'] as String,
    );

Map<String, dynamic> _$ProgramDefinitionToJson(ProgramDefinition instance) =>
    <String, dynamic>{
      'name': instance.name,
      'prnm': instance.prnm,
      'prcode': instance.prcode,
      'prstr': instance.prstr,
      'defaults': instance.defaults.toJson(),
      'allowed': instance.allowed.toJson(),
      'source': instance.source,
    };

ApplianceInfo _$ApplianceInfoFromJson(Map<String, dynamic> json) => ApplianceInfo(
      model: json['model'] as String,
      idMasked: json['id_masked'] as String,
    );

Map<String, dynamic> _$ApplianceInfoToJson(ApplianceInfo instance) =>
    <String, dynamic>{
      'model': instance.model,
      'id_masked': instance.idMasked,
    };

ProgramCatalog _$ProgramCatalogFromJson(Map<String, dynamic> json) =>
    ProgramCatalog(
      schemaVersion: (json['schema_version'] as num).toInt(),
      source: json['source'] as String,
      appliance:
          ApplianceInfo.fromJson(json['appliance'] as Map<String, dynamic>),
      importedAt: json['imported_at'] as String,
      programs: (json['programs'] as List<dynamic>)
          .map((e) =>
              ProgramDefinition.fromJson(e as Map<String, dynamic>))
          .toList(),
    );

Map<String, dynamic> _$ProgramCatalogToJson(ProgramCatalog instance) =>
    <String, dynamic>{
      'schema_version': instance.schemaVersion,
      'source': instance.source,
      'appliance': instance.appliance.toJson(),
      'imported_at': instance.importedAt,
      'programs': instance.programs.map((e) => e.toJson()).toList(),
    };
