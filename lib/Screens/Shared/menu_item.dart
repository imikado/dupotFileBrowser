import 'package:flutter/material.dart';

class MenuItem {
  MenuItem(
      {required this.icon,
      required this.label,
      required this.action,
      required this.pageSelected,
      required this.path});

  Icon? icon;
  String label;
  Function action;
  String pageSelected;
  String path;
}
