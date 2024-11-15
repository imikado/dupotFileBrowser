import 'package:dupot_file_browser/Process/commands.dart';
import 'package:dupot_file_browser/Process/paths.dart';
import 'package:dupot_file_browser/Screens/Shared/menu_item.dart';
import 'package:dupot_file_browser/Screens/Shared/sidemenu.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:package_info_plus/package_info_plus.dart';

class ContentWithSidemenu extends StatefulWidget {
  final Widget content;
  final String pageSelected;
  final String pathSelected;

  final Function handleGoToPath;
  final Function handleToggleDarkMode;
  final Function handleSetLocale;

  const ContentWithSidemenu(
      {super.key,
      required this.content,
      required this.pageSelected,
      required this.handleGoToPath,
      required this.handleToggleDarkMode,
      required this.handleSetLocale,
      required this.pathSelected});

  @override
  _ContentWithSidemenuState createState() => _ContentWithSidemenuState();
}

class _ContentWithSidemenuState extends State<ContentWithSidemenu> {
  List<MenuItem> stateMenuItemList = [];

  final FocusNode _focusNode = FocusNode();

  final alphanumeric = RegExp(r'^[a-zA-Z0-9]+$');

  String version = '';

  @override
  void initState() {
    super.initState();

    loadData();
  }

  Future<void> loadData() async {
    List<MenuItem> menuItemList = [
      MenuItem(
          icon: const Icon(Icons.home),
          label: 'Home',
          action: () {
            widget.handleGoToPath(Paths().homePath);
          },
          pageSelected: 'path',
          path: Paths().homePath),
    ];

    setState(() {
      stateMenuItemList = menuItemList;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).primaryColorDark,
        //leading: const Icon(Icons.home),
        title: Text(
          'File browser',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        leading: Builder(
          builder: (context) {
            return IconButton(
              color: Theme.of(context).primaryTextTheme.titleLarge!.color,
              icon: const Icon(Icons.menu),
              onPressed: () {
                Scaffold.of(context).openDrawer();
              },
            );
          },
        ),
        actions: [
          IconButton(
              onPressed: () {
                widget.handleToggleDarkMode();
                print('siwth dark');
              },
              icon: Icon(Icons.dark_mode)),
        ],
      ),
      resizeToAvoidBottomInset: true,
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: KeyboardListener(
          focusNode: _focusNode,
          autofocus: true,
          onKeyEvent: (event) {
            if (event is KeyDownEvent &&
                alphanumeric.hasMatch(event.logicalKey.keyLabel.toString())) {
              //widget.handleGoToSearch(event.logicalKey.keyLabel.toString());
            }
          },
          child:
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Container(
                width: 240,
                child: SideMenu(
                  menuItemList: stateMenuItemList,
                  pageSelected: widget.pageSelected,
                )),
            const SizedBox(width: 10),
            Expanded(child: widget.content),
          ])),
    );
  }
}
