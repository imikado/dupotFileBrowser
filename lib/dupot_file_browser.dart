import 'dart:io';

import 'package:dupot_file_browser/Layout/content_with_sidemenu.dart';
import 'package:dupot_file_browser/Localizations/app_localizations_delegate.dart';
import 'package:dupot_file_browser/Models/settings.dart';
import 'package:dupot_file_browser/Process/commands.dart';
import 'package:dupot_file_browser/Process/parameters.dart';
import 'package:dupot_file_browser/Process/paths.dart';
import 'package:dupot_file_browser/Screens/loading.dart';
import 'package:dupot_file_browser/Views/home_view.dart';
import 'package:dupot_file_browser/Views/path_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

class DupotFileBrowser extends StatefulWidget {
  const DupotFileBrowser({super.key});

  @override
  _DupotFileBrowserState createState() => _DupotFileBrowserState();
}

class _DupotFileBrowserState extends State<DupotFileBrowser> {
  Locale stateLocale = const Locale.fromSubtags(languageCode: 'en');

  String statePageSelected = constPagePath;
  String statePathSelected = '';

  String statePreviousPageSelected = '';

  bool show404 = false;

  bool stateIsDarkMode = false;

  static const String constPagePath = 'path';

  @override
  void initState() {
    super.initState();

    Map<String, String> envVars = Platform.environment;

    Paths().homePath = envVars['HOME']!;

    setState(() {
      statePathSelected = Paths().homePath;

      stateLocale =
          Locale.fromSubtags(languageCode: Parameters().getLanguageCode());
      stateIsDarkMode = Parameters().getDarkModeEnabled();
    });
  }

  @override
  Widget build(BuildContext context) {
    ColorScheme lightColorScheme =
        ColorScheme.fromSeed(seedColor: const Color.fromARGB(255, 54, 79, 148));

    ThemeData lightTheme = ThemeData(
      brightness: Brightness.light,
      colorScheme: lightColorScheme,
      primaryColorLight: lightColorScheme.primaryContainer,
      primaryColor: lightColorScheme.primary,
      secondaryHeaderColor: lightColorScheme.secondary,
      canvasColor: lightColorScheme.surface,
      textTheme: const TextTheme(
          titleLarge: TextStyle(color: Colors.white),
          headlineLarge: TextStyle(color: Colors.black)),
      cardTheme: CardTheme(color: lightColorScheme.secondary),
      cardColor: lightColorScheme.surfaceBright,
      scaffoldBackgroundColor: lightColorScheme.primaryContainer,
      useMaterial3: true,
    );

    Color darkColor1 = const Color.fromARGB(255, 1, 2, 17);
    Color darkColor2 = const Color.fromARGB(255, 6, 40, 54);
    Color darkColor3 = const Color.fromARGB(255, 5, 6, 43);
    Color darkColor4 = const Color.fromARGB(255, 12, 51, 87);

    Color darkColorWhite = const Color.fromARGB(255, 255, 255, 255);

    const TextStyle darkTextWhite = TextStyle(color: Colors.white);

    ThemeData darkTheme = ThemeData(
      brightness: Brightness.light,
      primaryColorDark: darkColor1,
      primaryColorLight: darkColor4,
      secondaryHeaderColor: darkColor1,
      canvasColor: darkColor1,
      textTheme: const TextTheme(
        titleLarge: darkTextWhite,
        titleMedium: darkTextWhite,
        titleSmall: darkTextWhite,
        headlineLarge: darkTextWhite,
        headlineMedium: darkTextWhite,
        headlineSmall: darkTextWhite,
        labelLarge: darkTextWhite,
        labelMedium: darkTextWhite,
        labelSmall: darkTextWhite,
        bodyLarge: darkTextWhite,
        bodyMedium: darkTextWhite,
        bodySmall: darkTextWhite,
        displayLarge: darkTextWhite,
        displayMedium: darkTextWhite,
        displaySmall: darkTextWhite,
      ),
      textSelectionTheme: TextSelectionThemeData(
          selectionColor: darkColor3, cursorColor: darkColorWhite),
      cardColor: darkColor1,
      scaffoldBackgroundColor: darkColor2,
      useMaterial3: true,
    );

    return MaterialApp(
      locale: stateLocale,
      theme: stateIsDarkMode ? darkTheme : lightTheme,
      localizationsDelegates: const [
        AppLocalizationsDelegate(),
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [
        Locale('en', 'EN'),
        Locale('fr', 'FR'),
        Locale('it', 'IT'),
      ],
      home: Navigator(
        pages: [
          if (statePageSelected == constPagePath)
            MaterialPage(
                key: const ValueKey(constPagePath),
                child: ContentWithSidemenu(
                    content: PathView(
                      path: statePathSelected,
                      handleGoToPath: _handleGoToPath,
                    ),
                    handleGoToPath: _handleGoToPath,
                    handleToggleDarkMode: _handleToggleDarkMode,
                    handleSetLocale: _handleSetLocale,
                    pageSelected: statePageSelected,
                    pathSelected: statePathSelected))
        ],
        onPopPage: (route, result) => route.didPop(result),
      ),
    );
  }

  void _handleToggleDarkMode() {
    if (stateIsDarkMode) {
      Parameters().setDarModeEnabled(false);
      setState(() {
        stateIsDarkMode = false;
      });
    } else {
      Parameters().setDarModeEnabled(true);
      setState(() {
        stateIsDarkMode = true;
      });
    }
  }

  void _handleGoToPath(String path) {
    setState(() {
      statePageSelected = constPagePath;
      statePathSelected = path;
    });
  }

  void _handleSetLocale(String locale) {
    Parameters().setLanguageCode(locale);
    setState(() {
      stateLocale = Locale.fromSubtags(languageCode: locale);
    });
  }
}
