import 'dart:io';

import 'package:dupot_file_browser/Process/commands.dart';
import 'package:dupot_file_browser/Process/parameters.dart';
import 'package:dupot_file_browser/Process/paths.dart';
import 'package:dupot_file_browser/dupot_file_browser.dart';
import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;

void main() async {
  try {
    WidgetsFlutterBinding.ensureInitialized();

    final Directory appDocumentsDir = await getApplicationDocumentsDirectory();
    String appDocumentsDirPath = appDocumentsDir.path;

    Directory documentsTargetDirectory =
        Directory(p.join(appDocumentsDirPath, "DupotFileBrowser"));

    if (!documentsTargetDirectory.existsSync()) {
      print('missing app directory, install database');
      await documentsTargetDirectory.create();
    } else {
      print('app directory already there');

      PackageInfo packageInfo = await PackageInfo.fromPlatform();

      File buildInstalled = File('${documentsTargetDirectory.path}/build.log');

      if (buildInstalled.existsSync()) {
        String buildInfo = buildInstalled.readAsStringSync();
        if (buildInfo == packageInfo.version) {
          print('build installed is the latest ($buildInfo)');
        } else {
          print(
              'build installed $buildInfo different current ${packageInfo.version}');
        }
      }

      Parameters('${documentsTargetDirectory.path}/parameters.json');
    }

    print('start application');

    runApp(const DupotFileBrowser());
  } on Exception catch (e) {
    print('Exception::');
    print(e);
  }
}
