import 'dart:io' as io;
import 'package:dupot_file_browser/Process/commands.dart';
import 'package:flutter/services.dart';

import 'dart:io';

class FirstInstallation {
  late Commands commands;

  FirstInstallation({required this.commands});

  Future<void> mkdir(String path) async {
    io.ProcessResult result =
        await commands.runProcessSync('/usr/bin/mkdir', [path]);
    print(result.stdout);
    print(result.stderr);
  }

  Future<void> copyTo(String fromPath, String targetPath) async {
    io.ProcessResult result = await commands.runProcessSync(
      '/usr/bin/cp',
      [fromPath, targetPath],
    );
    print(result.stdout);
    print(result.stderr);
  }

  Future<void> copyAssetTo(String assetPath, String targetPath) async {
    final bytes = await rootBundle.load(assetPath);
    final targetFile = File(targetPath);
    await targetFile.writeAsBytes(bytes.buffer.asUint8List());
  }
}
