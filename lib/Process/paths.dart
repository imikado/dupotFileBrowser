class Paths {
  String homePath = '';

  static final Paths _singleton = Paths._internal();

  factory Paths() {
    return _singleton;
  }

  Paths._internal();
}
