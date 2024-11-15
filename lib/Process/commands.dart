import 'dart:async';
import 'dart:io';

import 'package:dupot_file_browser/Models/settings.dart';

class Commands {
  static const String flatpakCommand = 'flatpak';

  late Settings settingsObj;
  late String updatesAvailableOutput;
  List<String> dbApplicationIdList = [];

  static final Commands _singleton = Commands._internal();

  factory Commands([Settings? settingsObj]) {
    if (settingsObj != null) {
      _singleton.settingsObj = settingsObj;
    }
    return _singleton;
  }

  Commands._internal();

  bool isInsideFlatpak() {
    return settingsObj.useFlatpakSpawn();
  }

  String getCommand(String command) {
    if (isInsideFlatpak()) {
      return settingsObj.getFlatpakSpawnCommand();
    }
    return command;
  }

  Future<ProcessResult> runProcess(
      String command, List<String> argumentList) async {
    return await Process.run(getCommand(command),
        getFlatpakSpawnArgumentList(command, argumentList));
  }

  Future<ProcessResult> runProcessSync(
      String command, List<String> argumentList) async {
    return Process.runSync(getCommand(command),
        getFlatpakSpawnArgumentList(command, argumentList));
  }

  List<String> getFlatpakSpawnArgumentList(
      String command, List<String> subArgumentList) {
    if (isInsideFlatpak()) {
      List<String> argumentList = [];
      argumentList.add('--host');
      argumentList.add(command);

      for (String subArgumentLoop in subArgumentList) {
        argumentList.add(subArgumentLoop);
      }
      return argumentList;
    }
    return subArgumentList;
  }

  Future<void> run(String applicationId) async {
    runProcess(flatpakCommand, ['run', applicationId]);
  }
}

class FlatpakApplication {
  final bool isInstalled;
  final String flatpakOutput;

  FlatpakApplication(this.isInstalled, this.flatpakOutput);
}
