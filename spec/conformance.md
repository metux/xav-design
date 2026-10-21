# Compute-Referenzablauf

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

# Konformität und Tests

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
- Destroy einer von einem `RECORDING`-Command-Buffer referenzierten Ressource wird atomar abgewiesen.
- Destroy einer von einem nicht-pending `EXECUTABLE`-Command-Buffer referenzierten Ressource invalidiert diesen Command Buffer.
- `DestroyCommandPool`, `DestroyDescriptorPool` und `FreeDescriptorSets` werden bei verbotener Pending-/Recording-Referenz atomar abgewiesen; erfolgreiche Kaskaden invalidieren alle betroffenen XIDs.
- `DestroyBuffer` während Pending-Use wird abgewiesen; nach erfolgreicher Zerstörung verhindern stale Descriptor-Slots eine neue Submission, bis sie aktualisiert oder freigegeben werden.
- `FreeMemory` bei gebundenem Buffer ergibt `BadMatch`; die Allokation kann erst nach Zerstörung aller gebundenen Buffer freigegeben werden.
- Device Loss macht alle angenommenen nicht-terminalen Submissions fehlgeschlagen, setzt zugehörige Fences auf `FAILED`, invalidiert betroffene Command Buffer nach der Pending-Phase und erzeugt keine erfolgreiche Completion.
- XID-Wiederverwendung bei ausstehender Arbeit
- Device Removal und Device Loss
- Korrekte XGE-Längen und Event-Feldpositionen
- Keine verspäteten X11-Fehler für angenommene asynchrone Requests
- Korrekte Berechnung von `C[i] = A[i] + B[i]`
