# OnionDrop Standalone für Android · 0.2.0 Alpha

Eigenständige Android-App mit dem unveränderten Original-Logo von OnionDrop.
Tor und Dateiübertragung laufen auf dem Handy. Kein Umbrel, eigener Server,
Orbot oder Benutzerkonto ist erforderlich.

**Lieferstatus:** implementierter und gegen Android API 35 kompilierter Quellcode.
43 lokale Kernprüfungen bestanden. **Keine APK im Paket.** Der vollständige
Android-/NDK-Build und eine echte Tor-Übertragung auf einem Android-Gerät wurden
noch nicht durchgeführt. Die Alpha ist deshalb noch keine einsatzgeprüfte App.

## Funktionen

- Native dunkle Oberfläche mit Original-Logo, Tor-Status und drei Bereichen:
  Übersicht, Senden, Empfangen.
- Dateien über Androids Dateiauswahl oder das Teilen-Menü übernehmen.
- Ausgewählte Dateien über einen geheimen Onion-Link freigeben.
- Separater geheimer Empfangslink: Besucher können Dateien abgeben, aber keine
  zuvor empfangenen Dateien sehen oder herunterladen.
- Links kopieren, teilen oder als lokal erzeugten QR-Code anzeigen.
- Empfangene Dateien über den Android-Speicherdialog exportieren.
- SHA-256-Prüfsummen, lokale Dateiverwaltung und Entfernen von Dateien.
- Sichtbarer Vordergrunddienst mit Stopp-Aktion und 30-Minuten-Sitzungsdauer.
- Neue Onion-Adresse und getrennte 256-Bit-Linkcodes pro Sitzung.
- Originale bleiben beim Entfernen einer Sende-Auswahl erhalten.

Die Empfangsseite verwendet JavaScript und kann im Tor Browser geöffnet werden.
Der Download einer bereitgestellten Datei benötigt kein JavaScript.
Es gibt keine native Funktion zum Hochladen an beliebige fremde OnionShare-Links.
Die App implementiert ihren eigenen Datei-Webdienst über Tor. OnionShare-
Konfigurationsimport, private Tor-Client-Authentifizierung und vollständige
Protokollkompatibilität mit OnionShares Verwaltung sind **nicht** implementiert.

## Speicher und Laufzeit

Die App speichert Dateien in ihrem privaten App-Verzeichnis. Bis zu 250 MiB pro
Datei, insgesamt bis zu 1 GiB / 100 Dateien je Bereich. Beim Deinstallieren werden
App-Dateien gelöscht; benötigte empfangene Dateien vorher exportieren.

Eine Freigabe läuft maximal 30 Minuten und kann jederzeit gestoppt werden.
Androids Energiesparen, Netzabbrüche und Vordergrunddienstlimits können sie früher
beenden. Abgebrochene Empfangsdateien werden nicht als vollständige Dateien
angezeigt. Tor startet nicht automatisch beim Booten oder nach einem Prozessabbruch.

Jeder, der den vollständigen Link kennt, erhält die entsprechende Sende- oder
Empfangsberechtigung. Der Link ist deshalb vertraulich. Die App nutzt keine
Cloudspeicherung, Werbung oder Analyse-Dienste. Eine formale Sicherheitsprüfung
ist noch nicht erfolgt.

## APK lokal bauen (ohne GitHub-Konto)

1. JDK 17 und Gradle 8.11.1 installieren.
2. Android SDK mit `platforms;android-35`, `build-tools;35.0.0` und NDK
   `28.2.13676358` installieren.
3. Die unten genannten nativen Build-Werkzeuge installieren.
4. Tor aus der festgelegten Quelle bauen, dann die App bauen.

Unter Linux, oder unter Windows mit WSL2/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y autoconf automake libtool autopoint gettext \
  pkg-config build-essential po4a libzstd-dev

# Auf die eigene SDK-Installation anpassen:
export ANDROID_HOME="$HOME/Android/Sdk"
export ANDROID_NDK_HOME="$ANDROID_HOME/ndk/28.2.13676358"

cd android-standalone
bash scripts/build-native-tor.sh arm64-v8a
bash tests/run.sh
gradle --no-daemon :app:assembleDebug :app:lintDebug
```

Für Emulatoren mit Intel/AMD zusätzlich `x86_64` an das Build-Skript übergeben.
Der native Tor-Build benötigt eine Internetverbindung, ausreichend freien
Speicher und mehr Zeit als der eigentliche App-Build. Das Skript verwendet die
Build-Regeln des Guardian Project und ist hier noch nicht vollständig ausgeführt
worden; eventuelle Build-Probleme müssen bei diesem ersten Durchlauf geprüft werden.

APK-Ausgabe:
`android-standalone/app/build/outputs/apk/debug/app-debug.apk`

Projektordner für Android Studio: `android-standalone/`. Es liegt kein Gradle-
Wrapper bei; Gradle 8.11.1 verwenden oder mit installiertem Gradle
`gradle wrapper --gradle-version 8.11.1` ausführen.

Unter Windows ist für den **nativen Tor-Build** WSL2/Linux vorgesehen; Git Bash
allein genügt für die Linux-NDK-Build-Schritte nicht.

## Optionaler GitHub-Build

Der zusätzliche Workflow `.github/workflows/android-standalone.yml` baut zuerst
Tor und danach die Debug-APK. Er kann in das bestehende OnionDrop-Repository
übernommen werden und bietet unter Actions einen manuellen Start.
Eine GitHub-Verbindung ist zur Nutzung des Quellcodes oder zum lokalen Bauen nicht
notwendig. Es wurde nichts auf GitHub hochgeladen und kein Workflow gestartet.

Das Ergebnis ist eine Test-APK. Für eine dauerhaft updatefähige Veröffentlichung
ist ein eigener, sicher verwahrter Signierschlüssel erforderlich. Die
Application-ID `de.dennysubke.oniondrop.standalone` ist von der früheren
Server-Client-Preview getrennt.

## Tor-Basis und Build-Grenze

Tor-Version: **0.4.9.12**.
Guardian-Project-Quellstand:
`cb04167d313cc3b5e1c1246111591aa57c2147cb`

Das Skript übernimmt die festgelegten Unterprojekte dieses Commits. Es verwendet
absichtlich kein älteres vorgebautes Tor-Paket als automatischen Ersatz.
Die native ausführbare `libtor.so` wird in die APK eingebettet und aus dem
Android-Native-Library-Verzeichnis gestartet. Ein Build ohne Tor-Binärdatei wird
abgebrochen, damit keine scheinbar eigenständige, aber unvollständige APK entsteht.

Anwendungsseitige Tor-Steuerung: Cookie-Authentifizierung auf Loopback,
`ADD_ONION` für eine nur während der Sitzung bestehende v3-Onion-Adresse und
`HS_DESC UPLOADED` vor der Anzeige des fertigen Links.

## Nachgewiesene Prüfungen

- 43 lokale Prüfungen: Tokenprüfung, Sonderzeichen, HTML-Escaping, zufällige
  Speicherpfade, Upload/Download, Download nur freigegebener Dateien,
  Empfang ohne öffentliche Dateiliste, Größenlimits, unvollständige Uploads,
  Herkunftsprüfung, doppelte Header, unbekannte Transferkodierungen,
  Link-Deaktivierung, Dateipersistenz sowie Tor-Control-Antworten und Ereignisse.
- Kompilierung sämtlicher App-Klassen gegen Android API 35, inklusive ZXing 3.5.3.
  Dabei wurden Ressourcen-IDs als Compiler-Platzhalter bereitgestellt; dies ist
  **kein** Android-Ressourcen- oder APK-Build.
- XML-Syntax von Manifest und Ressourcen geprüft.
- Das eingebundene Original-SVG ist bytegleich mit `oniondrop/static/logo.svg`.
  Die Android-PNG wurde aus diesem SVG gerendert, nicht neu gezeichnet.

Noch offen: NDK-/Gradle-/APK-Build, Android-Lint, echte Geräte- und
Hintergrundtests, Tor-Start und Veröffentlichung, Ende-zu-Ende-Transfers über Tor,
Android-Dateiauswahl, Teilen-Menü, Benachrichtigungen und QR-Scan auf dem Gerät.

## Quellen und Lizenzen

- OnionDrop und Original-Logo: https://github.com/dennysubke/oniondrop
- Tor für Android: https://github.com/guardianproject/tor-android
- Tor-Steuerprotokoll: https://spec.torproject.org/control-spec/
- Android-Vordergrunddienste:
  https://developer.android.com/develop/background-work/services/fgs/service-types
- ZXing 3.5.3: https://github.com/zxing/zxing/tree/zxing-3.5.3

OnionDrop: GPL-3.0-or-later, siehe LICENSE im Paket.
Weitere Hinweise in THIRD-PARTY-NOTICES.md.
