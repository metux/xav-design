# 14. Compute-Referenzablauf

Ziel-Workload:

`C[i] = A[i] + B[i]`

Typischer Ablauf:

1. Physical Device enumerieren oder Default Device erstellen.
2. Memory-Properties abfragen und logisches Device mit Compute-Queue erstellen.
3. A-, B- und C-Buffer erstellen.
4. Memory-Anforderungen abfragen, Speicher allozieren und Buffer binden.
5. A und B mit unabhängigen `WriteBuffer`-Requests hochladen.
6. Shader Module erstellen.
7. Descriptor Set Layout, Descriptor Pool und Descriptor Set erstellen.
8. Pipeline Layout und Compute Pipeline erstellen.
9. Descriptor Set mit A, B und C aktualisieren.
10. Command Pool und Command Buffer erstellen.
11. Pipeline binden.
12. Descriptor Sets binden.
13. Bei Bedarf Push Constants setzen.
14. `Dispatch` aufzeichnen und Command Buffer finalisieren.
15. Fence/Semaphoren erstellen, sofern erforderlich.
16. `QueueSubmit` ausführen.
17. Completion mit Fence oder Semaphore abwarten.
18. C über `ReadBuffer` zurücklesen.
19. Ressourcen nach den Lebenszyklusregeln zerstören.

Der Server muss sicherstellen, dass die Descriptoren zum Shader passen, statisch verwendete Ressourcen vorhanden sind und Dispatch-Limits eingehalten werden.

# 15. Konformität und Tests

Eine Implementierung sollte mindestens folgende Fälle testen:

- Exakte Request-Längen, Counts und Padding
- Byteordnung und feste Wire-Feldbreiten
- Reservierte Felder und unbekannte Flags
- Ungültige XIDs, Ressourcentypen und Ownership
- Cross-Device-Verwendung
- Atomare Create-, Update- und Submit-Operationen
- Überlauf- und Grenzfälle bei Buffer-Bereichen
- Memory-Alignment und Memory-Type-Kompatibilität
- Command-Buffer-Zustandsübergänge
- Fence- und Semaphore-Zustände sowie Timeouts
- Descriptor-Update/Freigabe während Pending-Use
- Ressourcenzerstörung bei internen Referenzen
- XID-Wiederverwendung bei ausstehender Arbeit
- Device Removal und Device Loss
- Korrekte XGE-Längen und Event-Feldpositionen
- Keine verspäteten X11-Fehler für angenommene asynchrone Requests
- Korrekte Berechnung von `C[i] = A[i] + B[i]`

# 16. Offene Punkte vor dem Einfrieren von v0.1

1. Zentrale numerische Subopcode-Registry für alle Requests.
2. Endgültige Request-Layouts für Shader Module, Command Pools, generische Zerstörung und Descriptor Set Layouts.
3. Event-Auswahl-Request-Layouts und Event-Registrierung.
4. Vollständige Property-Namen-/Atom-Registry.
5. Numerische Registries für Descriptor-Typen, Shader-Stages, Feature-IDs, Device-Typen und Queue-Flags.
6. Vollständige request-spezifische X11-Fehlerzuordnung.
7. Recovery-Verhalten, wenn ein späterer Command-Buffer-Chunk fehlschlägt.
8. Finaler Command-Buffer-Zustand nach asynchronem Fehler oder Device Loss.
9. Exakte Pending-Zerstörungsregeln für Pipeline, Pipeline Layout, Fence und Semaphore.
10. Semantik von `memory_properties_flags`.
11. Fehlerdarstellung für nicht unterstützte Device-Features und Extensions bei `CreateDevice`.
12. Exakte Pending-Signal-/Wait-Regeln für Binary-Semaphoren.
13. Vergabe, Eindeutigkeit und Wrap-Verhalten von `submission_id`.
14. Exakte Completion-/Failure-Event-Auslieferungsregeln.
15. Timeout-Grenzen und Scheduling-Garantien.
16. Verhalten der Device-Zerstörung bei asynchronen Teardown-Fehlern.
17. Ownership bei zukünftigen X11-Ressourcen-Sharing-Mechanismen.
18. Wire-Repräsentation von Physical-Device-UUID und Driver-UUID.
19. Queue-übergreifende Reichweite der `WriteBuffer`-Sichtbarkeitsgarantie.
20. Finale Vulkan-Stage-Zuordnung und zulässige Wait-Stage-Masks.
21. Vollständige, normative Definition der zentralen Ressourcenzustandsmaschine.
22. Exakte Vulkan-Lebensdauerprüfung für alle Resource-Kombinationen, bevor die Spezifikation als stabil gilt.

---

## Anhang A. Aktuelle zentrale Fehler-Offsets

| Offset | Symbol |
|---:|---|
| 0 | `DEVICE_UNAVAILABLE` |
| 1 | `DEVICE_LOST` |
| 2 | `INVALID_SYNCHRONIZATION_STATE` |
| 3 | `EXECUTION_FAILED` |
| 4 | `TRANSFER_FAILED` |
| 5 | `ALLOCATION_FAILED` |
| 6 | `DEPENDENCY_FAILED` |
| 7 | `INTERNAL_SERVER_ERROR` |

## Anhang B. Festgehaltene Designentscheidungen

- X11 ist der Transport; Vulkan-Handles bleiben serverseitig.
- Erste Implementierung: Xvfb, Compute-only.
- Kein Queue-XID; Queue-Adressierung über Device/Familie/Index.
- Physical Devices verwenden serverseitige XIDs.
- `CreateDefaultDevice` und explizites `CreateDevice` sind vorgesehen.
- Images gehören nicht zum v0.1-Compute-Pfad.
- `WriteBuffer` verwendet unabhängige Requests, keine Upload-Transaktion.
- `QueueSubmit`-Annahme und GPU-Completion sind unterschiedliche Ereignisse.
- Asynchrone Fehler werden über XAverius-Events gemeldet.
- Öffentliche Ressourcen-XIDs werden bei erfolgreicher Zerstörung sofort ungültig.
- Interne Vulkan-Objekte dürfen bis zur sicheren Freigabe weiterleben.
- Descriptor Sets dürfen während Pending-Use weder aktualisiert noch freigegeben werden.
- Wire-Layouts sind explizit und unabhängig von nativen C-Strukturen.
- Noch nicht zugewiesene Registry-Werte bleiben offen.

**Ende des konsolidierten Arbeitsentwurfs.**


