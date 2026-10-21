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
- `ShaderModuleData`: Einzelrequest CREATE|FINAL, mehrteiliger Upload, exakte Konkatenation ohne Paddingbytes, gültige Flag-Kombinationen und Null-Padding
- Fehler in einem Shader-Chunk verwirft das gesamte Assembly; FINAL-Fehler hinterlässt kein live Shader Module; ABORT gibt Assembly-Speicher frei
- Upload-Grenzen und aggregierte Assembly-Speicherlimits werden vor Allokation geprüft
- `CreateCommandPool` prüft Queue-Family-Index und reservierte Pool-Flags; `DestroyCommandPool` invalidiert alle Kinder atomar
- `CommandBufferData` validiert alle Entries eines Chunks vor dem Anhängen; bei einem ungültigen Chunk wird nichts aus diesem Chunk angehängt
- Nach fehlgeschlagenem CommandBufferData-Chunk bleiben zuvor akzeptierte Chunks erhalten; ein korrigierter Chunk kann folgen oder ABORT setzt den Buffer auf INITIAL zurück
- Fehlgeschlagenes CREATE hinterlässt keinen Command Buffer; fehlgeschlagenes FINAL lässt den bestehenden Buffer RECORDING
- ABORT ist bei INITIAL, EXECUTABLE, INVALID oder PENDING unzulässig und ändert keinen Zustand
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
- Wenn Backend-Quieszenz nach Device Loss nicht nachweisbar ist, werden interne Ressourcen quarantänisiert und weder freigegeben noch wiederverwendet, bis Quieszenz nachgewiesen oder der Serverprozess beendet ist.
- XID-Wiederverwendung bei ausstehender Arbeit
- Device Removal und Device Loss
- Korrekte XGE-Längen und Event-Feldpositionen
- Keine verspäteten X11-Fehler für angenommene asynchrone Requests
- Ein terminaler interner Submission-Ausgang auch dann, wenn das zugehörige Event nicht ausgewählt ist; bei ausgewähltem Event genau eine Zustellung des passenden Completion- oder Failure-Events
- Erfolgreiches `WriteBuffer` wartet auf alle zuvor angenommenen Submissions desselben logischen Devices, bevor es den Zielbereich verändert; dies gilt auch bei früherer Arbeit auf einer anderen Queue und bei überlappenden Buffer-Bereichen
- Jede nach erfolgreichem `WriteBuffer` angenommene Submission auf jeder Queue desselben logischen Devices sieht die hochgeladenen Bytes, ohne clientseitige Semaphore oder Barrieren allein für diese Sichtbarkeit
- Ein vorheriger fehlgeschlagener Submission-Ausgang verhindert `WriteBuffer` nicht, sofern das Device weiter verwendbar ist; der Upload erfolgt danach und spätere Submissions sehen die neuen Bytes
- Bei Device Loss oder fehlgeschlagenem Transfer sendet `WriteBuffer` keinen erfolgreichen Reply
- Ein früherer QueueSubmit wartet auf ein Timeline-Signal, das erst durch einen späteren `SignalSemaphore`-Request derselben Verbindung geliefert wird: `WriteBuffer` darf den Dispatcher nicht deadlocken; das Signal wird ausgeführt, die frühere Submission kann terminal werden, und spätere `QueueSubmit`-Requests passieren die Upload-Grenze erst nach erfolgreichem Reply
- `WriteBuffer` auf einem logischen Device erzeugt keine implizite Synchronisation mit einem anderen logischen Device auf derselben physischen GPU
- `ReadBuffer` wartet auf alle zuvor angenommenen Submissions desselben logischen Devices und auf relevante vorherige `WriteBuffer`-Transfers
- Readback-Ergebnisse werden nicht als korrekt vorausgesetzt, wenn fehlgeschlagene frühere GPU-Arbeit den gelesenen Bereich hätte verändern können
- Korrekte Berechnung von `C[i] = A[i] + B[i]`
