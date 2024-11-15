import 'package:dupot_file_browser/Localizations/app_localizations.dart';
import 'package:dupot_file_browser/Screens/Shared/menu_item.dart';
import 'package:flutter/material.dart';

class SideMenu extends StatelessWidget {
  const SideMenu({
    super.key,
    required this.menuItemList,
    required this.pageSelected,
  });

  final List<MenuItem> menuItemList;
  final String pageSelected;

  Widget getIcon(MenuItem menuItem) {
    if (menuItem.icon != null) {
      return menuItem.icon!;
    }
    return SizedBox();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
        padding: const EdgeInsets.all(5),
        child: Card(
            color: Theme.of(context).primaryColorLight,
            margin: const EdgeInsets.all(0),
            elevation: 5,
            child: ListView(
              children: menuItemList.map((menuItemLoop) {
                bool isSelected = false;
                if (menuItemLoop.pageSelected == pageSelected) {
                  isSelected = true;
                }

                return ListTile(
                    tileColor: isSelected
                        ? Theme.of(context).primaryColorDark
                        : Theme.of(context).primaryColorLight,
                    titleTextStyle: TextStyle(
                        color:
                            Theme.of(context).textTheme.headlineLarge!.color),

                    // selected: menuItemLoop.label == selected,
                    onTap: () {
                      menuItemLoop.action();
                    },
                    title: Row(
                      children: [
                        getIcon(menuItemLoop),
                        const SizedBox(width: 8),
                        Text(
                          AppLocalizations().tr(menuItemLoop.label),
                          style: isSelected
                              ? TextStyle(
                                  backgroundColor: Theme.of(context)
                                      .textSelectionTheme
                                      .selectionHandleColor)
                              : null,
                        ),
                      ],
                    ));
              }).toList(),
            )));
  }
}
