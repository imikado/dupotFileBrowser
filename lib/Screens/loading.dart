import 'package:dupot_file_browser/Process/commands.dart';
import 'package:dupot_file_browser/Process/first_installation.dart';
import 'package:dupot_file_browser/Process/parameters.dart';
import 'package:flutter/material.dart';

class Loading extends StatefulWidget {
  Loading({required this.handle});

  late Function handle;

  @override
  State<StatefulWidget> createState() => _Loading();
}

class _Loading extends State<Loading> {
  bool isLoaded = false;

  Future<void> processInit() async {
    print('Installation');

    print('End installation');

    setState(() {
      isLoaded = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!isLoaded) {
      processInit().then((value) {
        widget.handle();
      });
    }

    return Scaffold(
        backgroundColor: const Color.fromARGB(255, 205, 230, 250),
        body: Center(
          child: Column(
            children: [Image.asset('assets/logos/512x512.png')],
          ),
        ));
  }
}
