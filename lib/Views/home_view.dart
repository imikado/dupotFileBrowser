import 'package:flutter/material.dart';

class HomeView extends StatefulWidget {
  const HomeView({
    super.key,
  });

  @override
  State<HomeView> createState() => _HomeViewState();
}

class _HomeViewState extends State<HomeView> {
  List<String> stateCategoryIdList = [];
  String appPath = '';

  @override
  void initState() {
    super.initState();

    loadData();
  }

  Future<void> loadData() async {}

  @override
  Widget build(BuildContext context) {
    return Center(child: Text('text'));
  }
}
