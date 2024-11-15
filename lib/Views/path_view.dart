import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';

class PathView extends StatefulWidget {
  PathView({super.key, required this.path, required this.handleGoToPath});

  String path;
  Function handleGoToPath;

  @override
  State<PathView> createState() => _PathViewState();
}

class _PathViewState extends State<PathView> {
  final ScrollController scrollController = ScrollController();

  List<FileSystemEntity> stateFileList = [];

  String lastPathSelected = '';

  @override
  void initState() {
    super.initState();

    loadData();
  }

  Future<void> loadData() async {
    List<FileSystemEntity> fileList = Directory(widget.path).listSync();
    List<FileSystemEntity> filteredFileList =
        fileList.where((o) => !o.path.split('/').last.startsWith('.')).toList();
    filteredFileList.sort(
        (a, b) => a.path.split('/').last.compareTo(b.path.split('/').last));

    setState(() {
      stateFileList = filteredFileList;
    });
  }

  Widget getLine(FileSystemEntity file, FileStat fileStat) {
    String basename = file.path.split('/').last;

    if (fileStat.type.toString() == 'directory') {
      return Row(
        children: [
          Icon(Icons.folder),
          const SizedBox(
            width: 2,
          ),
          Text("$basename/"),
          const SizedBox(
            width: 2,
          ),
        ],
      );
    } else {
      return Row(
        children: [
          Icon(Icons.description),
          const SizedBox(
            width: 2,
          ),
          Text("$basename"),
          const SizedBox(
            width: 2,
          ),
        ],
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (lastPathSelected != widget.path) {
      loadData();
    }

    return Scrollbar(
        interactive: false,
        thumbVisibility: true,
        controller: scrollController,
        child: ListView.builder(
            itemCount: stateFileList.length,
            controller: scrollController,
            itemBuilder: (context, index) {
              FileSystemEntity fileLoop = stateFileList[index];
              FileStat fileStatLoop = fileLoop.statSync();

              return InkWell(
                  borderRadius: BorderRadius.circular(1.0),
                  onTap: () {
                    if (fileStatLoop.type.toString() == 'directory') {
                      widget.handleGoToPath(fileLoop.path);
                    }
                  },
                  child: Card(
                    color: Theme.of(context).cardColor,
                    child: Column(
                      children: [
                        Row(
                          children: [
                            const SizedBox(width: 20),
                            Expanded(child: getLine(fileLoop, fileStatLoop))
                          ],
                        ),
                      ],
                    ),
                  ));
            }));
  }
}
