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
- `ReadBuffer` wartet auf frühere angenommene Schreibzugriffe desselben logischen Devices auf den angeforderten Bereich, einschließlich anderer Queues; ein früherer Submission-Fehler verhindert den Read nicht allein, garantiert aber keine vom fehlgeschlagenen Schreibzugriff erwarteten Daten; bei Device Loss muss `ReadBuffer` mit `DEVICE_LOST` fehlschlagen und darf keinen erfolgreichen Daten-Reply senden
- `EnumeratePhysicalDevices` ist ein 8-Byte-Reply-Request; `DestroyDevice` ist ein 12-Byte-Void-Request
- `EnumeratePhysicalDevices.reply.length` entspricht der Summe der gepaddeten `PHYSICALDEVICEINFO`-Record-Längen geteilt durch vier; ohne Records ist es null
- `EnumeratePhysicalDevices` mit Request-Länge ungleich 8 Bytes ergibt `BadLength`; eine leere erfolgreiche Reply ist zulässig und darf keine unvollständigen Records enthalten
- `GetPhysicalDeviceQueueFamilyProperties.reply.length` entspricht `3 * queue_family_count`; die Payload-Länge muss durch 12 teilbar sein
- `GetPhysicalDeviceProperty` verwendet `SUCCESS = 0`, `NOT_SUPPORTED = 1`, `NOT_AVAILABLE = 2`; bei Nicht-Erfolg sind `property_type`, `value_length` und Payload null und `reply.length = 0`
- `GetPhysicalDeviceProperty` akzeptiert die vier kanonischen Namen aus der Property-Registry; Atom-IDs bleiben serverseitig vergeben. Unbekannte Atom-IDs ergeben `BadAtom`, gültige aber nicht registrierte Atom-Namen `NOT_SUPPORTED`, registrierte aber nicht verfügbare Properties `NOT_AVAILABLE`
- `XAverius.deviceUUID` und `XAverius.driverUUID` liefern bei Erfolg exakt 16 `BYTE_ARRAY`-Bytes; `XAverius.compute.maxWorkGroupInvocations` liefert einen `CARD32`; `XAverius.compute.maxWorkGroupSize` liefert genau drei `CARD32`-Werte in X/Y/Z-Reihenfolge. Der Reply-Typ und die exakte Wertlänge müssen zur Registry passen
- Die v0.1 Feature-ID- und Device-Extension-Registries sind leer: jede Feature-ID ergibt `BadValue`; syntaktisch gültige optionale Extension-Namen ergeben `BadMatch`; syntaktisch ungültige Extension-Namen ergeben `BadValue`; weder `CreateDevice` noch `CreateDefaultDevice` aktiviert optionale Features oder Extensions implizit
- `CreateDevice`-Länge entspricht exakt den drei geordneten variablen Record-Arrays; mindestens eine Queue-Family-Anforderung ist erforderlich; Queue-Prioritäten müssen endlich und in [0,1] liegen; unbekannte Feature-IDs, `enabled != 1`, doppelte Features/Extensions und syntaktisch ungültige Extension-Namen ergeben `BadValue`; registrierte, aber nicht unterstützte Features sowie unbekannte oder nicht unterstützte syntaktisch gültige Extensions ergeben `BadMatch`; jeder Fehler lässt die Create-XID unangelegt; `CreateDevice` und `CreateDefaultDevice` senden bei Erfolg keinen Reply
- `GetPhysicalDeviceMemoryProperties` liefert Memory-Type-/Heap-Indizes, die über die Lebensdauer der Physical-Device-XID stabil bleiben
- `AllocateMemory` hat exakt 32 Bytes; `allocation_size` muss positiv, `memory_type_index` gültig und das reservierte Feld null sein. Ungültige Werte ergeben `BadValue`, eine ungültige/belegte Ziel-XID `BadIDChoice`, unbekannte/nicht-live Device-XIDs `BadValue`, falsche live Ressourcentypen oder fremde Device-Ownership `BadMatch`, ein nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST` und Backend-Allokationsfehler `ALLOCATION_FAILED`; bei jedem Fehler bleibt die Ziel-XID unangelegt.
- `CreatePipelineLayout` prüft exakt `20 + 4 * set_layout_count + 12 * push_constant_range_count` Bytes, registrierte Stage-Bits, Push-Constant-Ranges, Device-/Set-Layout-Ownership und Ziel-XID-Kollisionen; unbekannte XIDs ergeben `BadValue`, falsche live Typen/fremde Ownership `BadMatch`, nicht verfügbare/verlorene Devices `DEVICE_UNAVAILABLE` / `DEVICE_LOST`, Backend-Allokationsfehler `ALLOCATION_FAILED`; Ablehnung hinterlässt kein Pipeline Layout.
- `CreateSemaphore` hat exakt 28 Bytes und akzeptiert nur `BINARY = 0` oder `TIMELINE = 1`; bei Binary muss `initial_value = 0` sein. Ungültige Felder ergeben `BadValue`, Ziel-XID-Kollision `BadIDChoice`, Backend-Allokationsfehler `ALLOCATION_FAILED`. Unbekannte Device-XIDs ergeben `BadValue`, falsche live Typen/fremde Ownership `BadMatch`, nicht verfügbare/verlorene Devices `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; bei Ablehnung bleibt die Ziel-XID unangelegt.
- `SignalSemaphore` prüft exakt 24 Bytes mit Präzedenz: Länge, Device-XID, Semaphore-XID, Typ/Ownership/Cross-Device, Device-Zustand, danach Timeline-Typ und Counter-/Reservierungsrelation. Bei gemischten Fehlern gewinnt die frühere Phase; insbesondere gewinnt `DEVICE_LOST` nach gültiger Ressourcenzuordnung gegen einen Binary-Semaphore-Typfehler. Eine synchrone Ablehnung verändert weder Counter noch Signalreservierungen.
- Timeline-Host-Signale müssen größer als der beobachtbare Counter und kleiner als jeder noch pending GPU-Signalwert sein; ein Signal, das über eine reservierte GPU-Signalstufe hinwegspringt, wird atomar mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen, ohne Counter- oder Reservierungsänderung.
- Ein Host-Signal auf einen Wert unterhalb einer höheren pending GPU-Signalreservierung darf einen darauf wartenden Queue-Wait freigeben; der GPU-Signalwert bleibt reserviert und kann danach erfolgreich signalisiert werden.
- `WaitForFence` prüft exakt 24 Bytes und löst Device-/Fence-XIDs vor der Wait-Registrierung auf; unbekannte XIDs ergeben `BadValue`, falsche live Typen/Ownership/Cross-Device `BadMatch`; Timeout, Ausführungsfehler, Device Loss und `DestroyDevice` werden über die festgelegten normalen Reply-Statuswerte zurückgegeben
- `WaitSemaphores` prüft exakt `28 + 12 * semaphore_count` Bytes; Präzedenz: Länge/Überlauf, Count/Modus/Duplikate, Device- und Semaphore-XIDs in Wire-Reihenfolge, Typ/Ownership/Cross-Device, Device-Zustand, zuletzt Timeline-Typ. Bei gemischten Fehlern gewinnt die frühere Phase; insbesondere gewinnt `DEVICE_LOST` nach gültigen XIDs und Ownership gegen einen Semaphore-Typfehler. Alle synchronen Ablehnungen erfolgen ohne Wait-Registrierung oder Zustandsänderung. Device Loss und `DestroyDevice` beenden bereits offene Waits terminal mit `DEVICE_LOST` beziehungsweise `DEVICE_DESTROYED`, ohne ein bereits serialisiertes Ergebnis zu überschreiben.
- `WaitSemaphores` blockiert den X11-Dispatcher nicht: ein späteres `SignalSemaphore` oder `QueueSubmit` derselben Verbindung kann den Wait erfüllen; die Timeout-Frist läuft ab Übernahme des Wait-Requests weiter.
- `WaitSemaphores` auf einen bislang nicht reservierten Timeline-Wert ist zulässig; bei endlichem Timeout endet er mit `TIMEOUT`, bei unbegrenztem Timeout bleibt er offen, bis der Wert erreicht oder das Device verloren wird. Der Server garantiert keinen Fortschritt, wenn kein späteres Signal eingereiht wird.
- Wenn `WriteBuffer` auf frühere Submissions wartet und ein zurückgestellter `QueueSubmit` einen Timeline-Wait einer früheren nicht-terminalen Submission erfüllen würde, ohne dass ein bereits angenommener Signalvorgang diesen Wait erfüllen kann, endet `WriteBuffer` mit `DEPENDENCY_FAILED`; der zurückgestellte Submit wird anschließend normal verarbeitet und nicht vor einem erfolgreichen Upload angenommen.
- `CreateFence` hat exakt 24 Bytes, `create_flags = 0` und `reserved = 0`; der Anfangszustand ist `UNSIGNALED`. Ungültige Felder ergeben `BadValue`, Ziel-XID-Kollision `BadIDChoice`, Backend-Allokationsfehler `ALLOCATION_FAILED`. Unbekannte Device-XIDs ergeben `BadValue`, falsche live Typen/fremde Ownership `BadMatch`, nicht verfügbare/verlorene Devices `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; bei Ablehnung bleibt die Ziel-XID unangelegt.
- `SelectEvents` hat exakt 32 Bytes und erfordert vorherige erfolgreiche XGE-1.0-Aushandlung; Scope-/Masken- und ungenutzte Feldkombinationen werden validiert. Jeder Fehler erhält die vorherige Event-Auswahl atomar unverändert.
- `ASYNC_ERROR` prüft die semantische Feldkombination: `origin = ORIGIN_QUEUE_SUBMIT` erfordert einen nicht-null Token einer zuvor angenommenen Submission; Token 0 bedeutet keine Submission-Zuordnung, und ein abgewiesener `QueueSubmit` darf nie als Token-Ziel eines `ASYNC_ERROR` erscheinen.
- `ASYNC_ERROR` mit nicht-null `submission_token` muss einer tatsächlich angenommenen Submission zugeordnet sein; unbekannte `origin`-Werte, nicht-null `reserved`-Felder und ungültige Device-/Ressourcenbezüge werden nicht serialisiert.
- Wenn die betroffene Ressource vor dem Linearisierungspunkt der `ASYNC_ERROR`-Einreihung zerstört oder ihre XID wiederverwendet wurde, muss `resource_xid = 0` sein; ein späterer Callback darf die numerische XID nicht auf das neue Objekt umbiegen.
- `SelectEvents` weist unbekannte Scope-Werte, nicht-null Flags/Common-Header-Reservierungen/Payload-Reservierungen, unbekannte Maskenbits und Scope-Felder mit falschen Nullwerten mit `BadValue` ab; falsche Live-Ressourcentypen oder fremde Ownership ergeben `BadMatch`. Jeder solche Fehler lässt die bisherige Maske unverändert.
- `SelectEvents` mit gültigem Device, aber nicht angeforderter Queue-Kombination wird mit `BadValue` abgewiesen; ein unbekanntes/nicht-live Device-XID ergibt `BadValue`, ein live XID falschen Typs oder fremder Ownership `BadMatch`.
- Nach erfolgreichem `DestroyDevice` dürfen auch nicht maskierbare `DEVICE_LOST`- und `ASYNC_ERROR`-Events keine zerstörte Device-XID als `device_xid` oder `resource_xid` enthalten; bereits vor dem Request eingereihte Events bleiben erhalten.
- Bei konkurrierendem `SelectEvents`, `DestroyDevice` und Submission-Abschluss entscheidet ein gemeinsamer serialisierter Linearisierungspunkt über Masken-Sampling und Event-Einreihung; ein späterer Backend-Callback darf unterdrückte Events nicht nachträglich einreihen.
- Für jede angenommene Submission wird höchstens eines von `SUBMISSION_COMPLETE` und `SUBMISSION_FAILED` als terminales Event eingereiht; `ASYNC_ERROR` ist nur ergänzende Diagnose und kein zweiter terminaler Ausgang.
- Nach erfolgreicher Verarbeitung von `DestroyDevice` werden keine neuen Events mit dessen zerstörter `device_xid` mehr erzeugt oder zugestellt; bereits zuvor in den X11-Ausgabestrom eingereihte Events bleiben unberührt. Die interne terminale Abwicklung angenommener Submissions und Backend-Referenzen bleibt unabhängig von dieser Event-Unterdrückung erhalten.
- Nach Client-Disconnect werden für die geschlossene Verbindung keine neuen XAverius-Events mehr eingereiht oder über andere Verbindungen zugestellt; Event-Auswahlen und öffentliche XID-Zuordnungen der Verbindung werden aus dem aktiven Verbindungszustand entfernt. Bereits angenommene Arbeit erreicht intern ihren tatsächlichen terminalen Ausgang, ohne Completion zu erfinden oder Backend-Ressourcen vorzeitig freizugeben; der Disconnect erzwingt kein unbegrenztes Warten.
- Client-Disconnect bricht offene serverseitige `WaitSemaphores`-/`WaitForFence`-Registrierungen ohne Reply ab, gibt nur die ausschließlich von diesen Waits gehaltenen Referenzen frei und verändert keine bereits angenommene GPU-Arbeit oder deren Synchronisationszustände.
- Konkurrierende Wait-Endbedingungen haben genau einen terminalen Ausgang: bereits festgestellte Erfüllung bleibt erfolgreich; andernfalls gewinnt der zuerst serialisiert festgestellte Timeout, Device Loss oder `DestroyDevice`-Übergang. Device Loss vor `DestroyDevice` ergibt `DEVICE_LOST`; ein noch offener Wait bei verarbeitetem `DestroyDevice` ergibt `DEVICE_DESTROYED`; spätere Übergänge überschreiben das Ergebnis nicht.
- `CreateBuffer` weist `usage_flags = 0` und unbekannte Usage-Bits mit `BadValue` ab
- `CreateBuffer` unterscheidet unbekannte/nicht-live Device-XIDs (`BadValue`), falsche live Ressourcentypen (`BadMatch`), nicht verfügbare/verlorene Devices (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`) und Backend-Speicherknappheit (`ALLOCATION_FAILED`); bei jedem Fehler bleibt die Ziel-XID unangelegt
- `CreateDescriptorPool` unterscheidet unbekannte Device-XIDs (`BadValue`), falsche live Typen/fremde Ownership (`BadMatch`), nicht verfügbare/verlorene Devices (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`) und Backend-Allokationsfehler (`ALLOCATION_FAILED`); bei Ablehnung bleibt die Pool-XID unangelegt.
- `CreateDescriptorPool`, `AllocateDescriptorSets` und `FreeDescriptorSets` weisen Count null mit `BadValue` ab; `AllocateDescriptorSets` unterscheidet unbekannte Eingabe-XIDs (`BadValue`), falsche live Typen/fremde Ownership (`BadMatch`), Device-Zustände (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`) und Pool-/Backend-Allokationsfehler (`ALLOCATION_FAILED`), und lässt bei Ablehnung keine Teilmenge live
- Alle Create-Ziel-XIDs werden getrennt von Eingabe-XIDs geprüft: ungültige/belegte Ziel-XIDs ergeben `BadIDChoice`; Batch-Erzeugung hinterlässt bei Kollision keine Teilmenge
- `ShaderModuleData` ohne passendes Upload-Assembly und `CommandBufferData` ohne passenden `RECORDING`-Buffer werden mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen; CREATE-XID-Kollisionen ergeben `BadIDChoice`
- `ShaderModuleData`: jeder fehlerhafte Chunk verwirft das gesamte Assembly; nach Disconnect oder Device Loss bleibt kein altes Assembly adressierbar, und spätere Chunks/ABORTs dürfen es nicht wiederbeleben
- `ShaderModuleData`- und `CommandBufferData`-Chunk-Fehler werden nur synchron als X11-Fehler gemeldet; sie erzeugen kein `ASYNC_ERROR`, da keine Submission angenommen wurde
- `CreateDevice` weist null Queue-Family-Records, null Queue-Anzahl und doppelte Queue-Family-Records mit `BadValue` ab; eine nicht unterstützte Queue-Anzahl ergibt `BadMatch`
- Binary-Semaphore: ein angenommener Wait konsumiert das Signal nicht vor tatsächlicher Erfüllung; das Signal wird genau einmal konsumiert und erst dann kann ein neuer Signalzyklus beginnen; doppelte pending Wait-/Signaloperationen werden atomar abgewiesen
- Timeline-Semaphore: angenommene, noch nicht terminale Signaloperationen reservieren ihre Werte, erhöhen den beobachtbaren Counter aber erst nach erfolgreicher Ausführung; neue Signalwerte müssen über allen pending reservierten Werten liegen
- Jede angenommene Queue-Wait-/Signaloperation hält eine Referenz auf die exakte interne Semaphore-Identität bis zum terminalen Operationsausgang und bis das Backend keinen Zugriff mehr ausführen kann; XID-Wiederverwendung darf diese Referenz nicht umleiten
- Doppelte Pool-Size-Typen, doppelte Descriptor-Updates desselben Slots, doppelte Wait-/Signal-Entries sowie eine Semaphore zugleich in Wait und Signal werden gemäß den Fehlerregeln atomar abgewiesen
- `CreateComputePipeline` verwendet die normative Länge `28 + ((entry_point_length + 3) & ~3)` und prüft nichtleeren ASCII-Entry-Point sowie Null-Padding; unbekannte Eingabe-XIDs ergeben `BadValue`, falsche live Typen/fremde Ownership `BadMatch`, nicht verfügbare/verlorene Devices `DEVICE_UNAVAILABLE` / `DEVICE_LOST`, Backend-Allokationsfehler `ALLOCATION_FAILED`; bei Ablehnung bleibt die Pipeline-XID unangelegt
- `DestroySemaphore` und `DestroyFence` sind jeweils 16-Byte-Void-Requests; `WaitSemaphores` verwendet `28 + 12 * semaphore_count`
- `DestroyFence` und `DestroySemaphore` prüfen die feste Request-Länge vor XID-Auflösung; unbekannte/nicht-live XIDs ergeben `BadValue`, falsche live Typen oder Ownership `BadMatch`, und Ablehnungen hinterlassen XIDs/Zustände unverändert
- `DestroyFence` wird abgewiesen, solange die Fence einer nicht-terminalen Submission zugeordnet ist oder eine offene `WaitForFence`-Registrierung dieselbe interne Fence-Identität referenziert; `DestroySemaphore` wird abgewiesen, solange Queue-Wait/-Signal, eine offene `WaitSemaphores`-Registrierung für dieselbe interne Semaphore-Identität oder eine andere aktive Host-Operation sie verwendet. Beide Ablehnungen sind atomar. Nach terminal festgestelltem Wait-Ergebnis blockiert ein noch ausstehender Reply die Zerstörung nicht
- `GetFenceStatus` ist ein 16-Byte-Reply-Request mit Fence-Status in Reply-Byte 1, `reply.length = 0` und null reservierten XAverius-Bytes in Offsets 8–31
- Error-Offsets und Event-/Reply-Statuswerte bleiben getrennte Namespaces: `EXECUTION_FAILED` ist Error-Offset 3, `WaitForFence`-Status 2 und `SUBMISSION_FAILED.failure_class` 0; `DEVICE_LOST` ist Error-Offset 1, `WaitForFence`-Status 3 und `SUBMISSION_FAILED.failure_class` 1. `DEVICE_LOST.reason_code` verwendet wiederum die eigene Reason-Code-Registry.
- `WaitSemaphores` und `WaitForFence` mit Timeout 0 prüfen den Zustand ohne absichtliches Warten; `UINT64_MAX` wartet unbegrenzt, andere Werte verwenden eine monotone Nanosekunden-Frist ab Ausführungsübernahme
- Eine endliche Wait-Frist wird bei internen Warteabschnitten oder Scheduler-Unterbrechungen nicht neu gestartet; die Antwort darf verspätet eintreffen, aber eine bereits erfüllte Bedingung gewinnt bei der abschließenden Zustandsprüfung gegen `TIMEOUT`
- `WaitSemaphores`-Timeout liefert Status `TIMEOUT` ohne Zustandsänderung; `WaitForFence` liefert `SUCCESS`, `EXECUTION_FAILED` oder `TIMEOUT` gemäß dem terminalen Fence-Zustand und der Frist, sowie `DEVICE_LOST` beziehungsweise `DEVICE_DESTROYED`, wenn einer dieser terminalen Übergänge zuerst festgestellt wird
- `DestroyFence` wird bei `PENDING` oder einer noch offenen `WaitForFence`-Registrierung atomar mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen; nach serialisiert festgestelltem terminalem Wait-Ergebnis blockiert ein nur noch ausstehender Reply die Zerstörung nicht
- `DestroySemaphore` wird bei einer offenen `WaitSemaphores`-Registrierung, die dieselbe interne Semaphore-Identität referenziert, atomar mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen; nach serialisiert festgestelltem terminalem Wait-Ergebnis blockiert ein noch ausstehender Reply die Zerstörung nicht
- Device Loss während eines blockierenden Waits wird nicht als Timeout maskiert: `WaitSemaphores` endet mit `DEVICE_LOST`-X11-Fehler, `WaitForFence` liefert `DEVICE_LOST` im Reply
- Verarbeitung von `DestroyDevice` beendet noch offene unbegrenzte Waits ohne auf GPU-Fortschritt zu warten: `WaitSemaphores` endet mit `DEVICE_DESTROYED`-X11-Fehler, `WaitForFence` liefert Reply-Status `DEVICE_DESTROYED`; bereits zuvor festgestellte erfüllte Bedingungen behalten ihr normales Ergebnis
- `GetFenceStatus` prüft exakt 16 Bytes und Device-/Fence-XIDs vor dem Reply; unbekannte XIDs ergeben `BadValue`, falsche live Typen/Ownership/Cross-Device `BadMatch`; nach Device Loss liefert die Abfrage den gespeicherten Zustand
- Nach Device Loss liefert `GetFenceStatus` den gespeicherten Zustand; Fences aus dadurch fehlgeschlagenen nicht-terminalen Submissions stehen auf `FAILED`, nicht eingereichte Fences werden nicht künstlich verändert. `WaitForFence` liefert nach erkanntem Device Loss stets `DEVICE_LOST`, ohne unbegrenzt weiterzuwarten
- `GetSemaphoreCounterValue` prüft exakt 16 Bytes und Device-/Semaphore-XIDs vor dem Reply; unbekannte XIDs ergeben `BadValue`, falsche live Typen/Ownership/Cross-Device `BadMatch`; der Request ist nur für Timeline-Semaphoren gültig
- Nach Device Loss liefert `GetSemaphoreCounterValue` keinen scheinbar erfolgreichen Counter-Reply, sondern `DEVICE_LOST`; `SignalSemaphore`, `QueueSubmit` und `WaitSemaphores` können Semaphore-Operationen nicht als erfolgreich fortgesetzt behandeln
- Device-Loss-Teardown invalidiert öffentliche Fence-/Semaphore-XIDs, darf aber interne Synchronisationsobjekte erst freigeben, wenn Backend-Zugriffe und serverseitige Operationen sicher beendet sind oder die Objekte gemäß den Quarantäneregeln isoliert bleiben
- `CommandBufferData`-ABORT hat exakt 16 Bytes; andere Chunks enthalten nur vollständige Entries
- `CommandBufferData` akzeptiert exakt die Flag-Kombinationen `000` (Append), `010` (FINAL), `100` (CREATE), `110` (CREATE|FINAL) und `001` (ABORT); jede andere Kombination sowie reservierte Flag-Bits ergeben `BadValue`.
- `CommandBufferData` prüft die Ziel-XID vor der Pool-XID: CREATE mit ungültiger/belegter Ziel-XID ergibt `BadIDChoice`; ohne CREATE ergeben unbekannte Buffer-XIDs `BadValue`. Unbekannte Pool-XIDs ergeben `BadValue`, falsche live Typen, fremde Ownership oder eine nicht zum Buffer gehörende Pool-XID ergeben `BadMatch`.
- `CommandBufferData`-Fehlerpräzedenz: fehlerhafte Request-/Entry-Struktur (`BadLength`) schlägt ungültige Flags, reservierte Bits, Padding und Command-ID/Werte (`BadValue`); diese Feldfehler schlagen XID-Fehler. Danach wird die Ziel-XID vor der Pool-XID geprüft, und Typ/Ownership vor Device-/Buffer-Zustand.
- Bei `CommandBufferData` mit ungültiger Flag-Kombination und ungültiger Ziel-XID gewinnt `BadValue`; bei strukturell abgeschnittenem Entry und ungültiger Ziel-XID gewinnt `BadLength`; bei CREATE mit gültigen Flags und ungültiger/belegter Ziel-XID gewinnt `BadIDChoice` vor einem ungültigen Pool-XID.
- Bei CREATE/Append/FINAL auf einem verlorenen Device gewinnt `DEVICE_LOST` nach gültiger XID-/Typ-/Ownership-Prüfung auch dann, wenn ein bestehender Buffer nicht `RECORDING` ist. ABORT bleibt die Ausnahme: nach Device Loss wird weiterhin der Pool-/Buffer-Bezug und `RECORDING`-Zustand geprüft; ungültiger Zustand ergibt `INVALID_SYNCHRONIZATION_STATE`.
- Auch bei `ABORT` muss `command_pool_xid` exakt dem Eltern-Pool des Buffers entsprechen; falsche Pool-Zuordnung wird abgewiesen, ohne Recording, Entries oder Referenzen zu verändern.
- Ein Entry mit unvollständigem Header oder deklarierter Länge über das Request-Ende hinaus ergibt `BadLength`; Länge null, Länge kleiner als der Entry-Header und unbekannte Command-ID ergeben `BadValue`. In allen Fällen wird kein Teil des aktuellen Chunks angehängt.
- `ResetCommandBuffer` prüft Request-Länge, XIDs, Typ, Ownership und Cross-Device-Zuordnung vor Zustandsänderungen; nach erfolgreicher XID-Prüfung ergeben ein nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; fehlende Reset-Berechtigung und PENDING ergeben `INVALID_SYNCHRONIZATION_STATE`, wobei Zustand, Entries und Referenzen unverändert bleiben.
- `QueueSubmit`-Länge stimmt exakt mit `40 + 4*C + 16*W + 12*S` überein; Null- und wiederverwendete Submission-Tokens ergeben `BadValue`; Counts/Längenüberlauf ergeben `BadLength`; fremde Ownership/Queue ergeben `BadMatch`; ungültige Zustände ergeben `INVALID_SYNCHRONIZATION_STATE`; synchron abgewiesene Requests erzeugen kein Submission-Event
- `QueueSubmit`-Fehlerpräzedenz: fehlerhafte Gesamtlänge/Counts (`BadLength`) schlägt Token-/Masken-/reservierte-Feld-Fehler (`BadValue`); syntaktische Fehler schlagen XID-Auflösung; XID-/Typ-/Ownership-/Queue-Fehler schlagen Device- und Zustandsfehler.
- `QueueSubmit` mit Token `0` oder bereits verwendetem Token und gleichzeitig unbekannter Device-/Buffer-XID ergibt `BadValue` aus der Token-Prüfung; eine falsche Länge hat Vorrang vor beiden Fehlern.
- Bei gültiger Syntax und XIDs ergibt ein falscher live Ressourcentyp/fremde Ownership `BadMatch`, auch wenn das Device verloren ist. Nach gültiger XID-/Typ-/Ownership-/Queue-Prüfung ergibt Device Loss `DEVICE_LOST` vor einem nicht-`EXECUTABLE` Command Buffer, einer nicht submitbaren Fence oder einem ungültigen veränderlichen Semaphore-Zustand.
- Eine Wait-Stage-Maske mit reservierten Bits ergibt `BadValue` vor XID-/Zustandsprüfung; eine syntaktisch gültige, aber von der Queue-Family nicht unterstützte Stage ergibt `INVALID_SYNCHRONIZATION_STATE` erst nach XID-/Ownership- und Device-Prüfung.
- Nicht-null Binary-Wait-/Signalwerte und ungültige Timeline-Signalwerte werden erst nach XID-/Typ-/Ownership- und Device-Prüfung mit `BadValue` abgewiesen; bei einer Ablehnung bleiben zuvor geprüfte Command Buffer, Fence und Semaphore vollständig unverändert.
- Wenn mehrere Zustandsfehler gleichzeitig vorliegen, prüft `QueueSubmit` nach Device-Zustand zuerst die optionale Fence, dann Command Buffer in Array-Reihenfolge, danach Wait-Entries und zuletzt Signal-Entries in Array-Reihenfolge; innerhalb jedes Semaphore-Entries werden typabhängige Werte vor Stage-/Operationszustand geprüft.
- Ein fehlerhafter FINAL-Chunk von `CommandBufferData` lässt den Buffer `RECORDING`, erhält alle früher akzeptierten Entries/Referenzen und hängt weder Entries noch Referenzen aus dem fehlgeschlagenen Chunk an.
- `QueueSubmit` validiert alle Command Buffer und Synchronisationsobjekte vor dem Commit; wird ein späterer Eintrag abgewiesen, bleiben auch zuvor erfolgreich einzeln validierte Objekte unverändert.
- Bei abgewiesenem `QueueSubmit` bleibt jeder Command Buffer `EXECUTABLE`; keine Fence wird zugeordnet oder umgeschaltet, Semaphore-Counter/Signalverfügbarkeit/Pending-Slots/Timeline-Reservierungen bleiben unverändert und es entstehen keine internen Submission-Referenzen.
- Der `submission_token` wird erst bei Annahme verbraucht: nach einem synchron abgewiesenen Request kann derselbe Token in einem korrigierten Request verwendet werden; ein angenommener Request reserviert ihn genau einmal.
- Ein abgewiesener `QueueSubmit` erzeugt weder `SUBMISSION_COMPLETE`/`SUBMISSION_FAILED` noch `ASYNC_ERROR`; ein späterer Backend-Fehler einer angenommenen Submission folgt dagegen den terminalen Submission-Regeln.
- `QueueSubmit` weist doppelte Semaphore-XIDs innerhalb des Wait-Arrays oder des Signal-Arrays sowie dieselbe Semaphore in beiden Arrays vor Annahme atomar ab; der Fehler ist `BadValue`, und Command-Buffer-, Fence-, Semaphore- und Submission-Zustände bleiben unverändert
- `QueueSubmit` validiert die Semaphore-Typen und Werte vor Annahme: Binary-Wait-/Signalwerte müssen null sein; Timeline-Signalwerte müssen größer als Counter und alle zuvor reservierten pending GPU-Signalwerte sein; doppelte Timeline-Signal-Entries derselben Semaphore sind unzulässig
- Ein abgewiesener `QueueSubmit` reserviert weder `submission_token` noch Semaphore-Wait-/Signal-Slots und erzeugt weder Submission-Events noch interne Submission-Referenzen
- `QueueSubmit.wait_stage_mask` wird als XAverius-Bitmaske und nicht als rohe Vulkan-Maske interpretiert: `DRAW_INDIRECT=0x1`, `COMPUTE_SHADER=0x2`, `TRANSFER=0x4`, `ALL_COMMANDS=0x8`; die Backend-Übersetzung verwendet die zugehörigen Vulkan-Stage-Bits
- Wait-Stage-Masken mit Wert 0 oder reservierten Bits ergeben `BadValue`; die Ablehnung ist atomar und lässt Fence-/Semaphore-Zustände unverändert
- Auf einer Compute-Queue sind alle vier einzeln definierten Stage-Bits gültig; auf einer reinen Transfer-Queue sind nur `TRANSFER` und `ALL_COMMANDS` gültig; `COMPUTE_SHADER` auf einer Nicht-Compute-Queue sowie `DRAW_INDIRECT` ohne Graphics- oder Compute-Unterstützung ergeben `INVALID_SYNCHRONIZATION_STATE`
- Kombinierte Masken aus mehreren unterstützten Stages (z. B. `COMPUTE_SHADER | TRANSFER`) werden akzeptiert; auch `ALL_COMMANDS | COMPUTE_SHADER` wird akzeptiert und korrekt als OR der Vulkan-Stage-Bits übersetzt. Eine Maske mit einem nicht unterstützten Stage wird mit `INVALID_SYNCHRONIZATION_STATE` atomar abgewiesen
- `ShaderModuleData`: Einzelrequest CREATE|FINAL, mehrteiliger Upload, exakte Konkatenation ohne Paddingbytes, gültige Flag-Kombinationen und Null-Padding
- Fehler in einem Shader-Chunk verwirft das gesamte Assembly; FINAL-Fehler hinterlässt kein live Shader Module; ABORT gibt Assembly-Speicher frei
- Upload-Grenzen und aggregierte Assembly-Speicherlimits werden vor Allokation geprüft
- `CreateDescriptorSetLayout` prüft die exakte Länge `24 + 16 * binding_count`, `flags = 0`, Binding-Eindeutigkeit, positive Descriptor-Counts und unterstützte Descriptor-/Stage-Werte; unbekannte Device-XIDs ergeben `BadValue`, falsche live Typen/fremde Ownership `BadMatch`, nicht verfügbare/verlorene Devices `DEVICE_UNAVAILABLE` / `DEVICE_LOST` und Backend-Allokationsfehler `ALLOCATION_FAILED`; bei Ablehnung bleibt die Ziel-XID unangelegt
- Ein leeres Descriptor Set Layout mit `binding_count = 0` ist gültig; fehlerhafte Binding-Records oder nicht-null Layout-Flags hinterlassen kein öffentliches Objekt
- Ein nicht zum Count passender Payload ergibt `BadLength`; nicht unterstützte Flags, Typen oder Stage-Bits werden abgewiesen
- `CreateCommandPool` prüft Queue-Family-Index und reservierte Pool-Flags; unbekannte Device-XIDs und ungültige Queue-Family-Indizes ergeben `BadValue`, falsche live Typen/fremde Ownership `BadMatch`, nicht verfügbare/verlorene Devices `DEVICE_UNAVAILABLE` / `DEVICE_LOST`, Backend-Allokationsfehler `ALLOCATION_FAILED`; bei Ablehnung bleibt die Pool-XID unangelegt; `DestroyCommandPool` invalidiert alle Kinder atomar
- `CreateCommandPool` akzeptiert nur `TRANSIENT` und `RESET_COMMAND_BUFFER`; unbekannte Pool-Flags werden mit `BadValue` abgewiesen und nicht stillschweigend ergänzt
- `TRANSIENT` ändert keine beobachtbare Semantik; `RESET_COMMAND_BUFFER` und `TRANSIENT` sind unabhängig kombinierbar
- `ResetCommandBuffer` ohne `RESET_COMMAND_BUFFER` wird abgewiesen; mit Flag setzt es `INITIAL`, `RECORDING`, `EXECUTABLE` oder `INVALID` auf `INITIAL` und verwirft Entries samt aufgezeichneten Referenzen
- `ResetCommandBuffer` bei `PENDING` wird atomar abgewiesen; Zustand und Referenzen bleiben unverändert
- `CommandBufferData`-`ABORT` kann ein nicht-pending `RECORDING` unabhängig vom Pool-Reset-Flag auf `INITIAL` zurücksetzen, ist aber für andere Zustände unzulässig; es bleibt nach Device Loss als logische Bereinigung zulässig, sofern Buffer und Pool noch live sind und korrekt zusammengehören
- Nach Device Loss werden CREATE-/Append-/FINAL-Chunks von `CommandBufferData` mit `DEVICE_LOST` abgewiesen und verändern keine vorher akzeptierten Entries oder Referenzen; ABORT startet keine Vulkan-Arbeit
- `CommandBufferData` validiert alle Entries eines Chunks vor dem Anhängen; bei einem ungültigen Chunk wird nichts aus diesem Chunk angehängt
- Nach fehlgeschlagenem CommandBufferData-Chunk bleiben zuvor akzeptierte Chunks erhalten; ein korrigierter Chunk kann folgen oder ABORT setzt den Buffer auf INITIAL zurück
- Fehlgeschlagenes CREATE hinterlässt keinen Command Buffer; fehlgeschlagenes FINAL lässt den bestehenden Buffer RECORDING
- ABORT ist bei INITIAL, EXECUTABLE, INVALID oder PENDING unzulässig und ändert keinen Zustand
- Die zentrale Request-Registry enthält genau 40 eindeutige, explizit vergebene Subopcodes (1–40); Subopcode 0 ist reserviert, kein Wert ist doppelt vergeben, und spätere Requests dürfen bestehende Werte nicht verschieben oder wiederverwenden
- Die Command-Entry-Registry weist `CMD_BIND_PIPELINE`, `CMD_BIND_DESCRIPTOR_SETS`, `CMD_DISPATCH` und `CMD_PUSH_CONSTANTS` eindeutig die IDs 1–4 zu. ID 5 bezeichnet ausschließlich im presentation-capable Profil `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE`; ein Compute-only Server weist diesen Entry als unbekannte Command-ID mit `BadValue` zurück. ID 0 und alle sonstigen nicht zugewiesenen IDs ergeben `BadValue`
- Die Descriptor-Type-Registry definiert in v0.1 ausschließlich `STORAGE_BUFFER = 1`; `0` und alle nicht zugewiesenen Werte werden abgewiesen und niemals stillschweigend umgedeutet
- Die Shader-Stage-Registry definiert ausschließlich das `COMPUTE`-Bit `0x00000001`; andere Bits sind reserviert und müssen abgewiesen werden
- Queue-Flags werden gemäß der zentralen Registry übersetzt und zurückgegeben; Bits 5–31 sind null/reserviert
- `PHYSICALDEVICEINFO.device_type` enthält nur die registrierten Werte 0–4; unbekannte native Kategorien werden als `OTHER = 0` abgebildet
- Byteordnung und feste Wire-Feldbreiten
- Reservierte Felder und unbekannte Flags
- Ungültige XIDs, Ressourcentypen und Ownership
- Cross-Device-Verwendung
- Atomare Create-, Update- und Submit-Operationen
- Überlauf- und Grenzfälle bei Buffer-Bereichen
- `BindBufferMemory`: ungültige XIDs, falscher Typ/Ownership, bereits gebundener Buffer, Alignment, Memory-Type und Bounds werden jeweils dem festgelegten Fehlerpfad zugeordnet; bei Ablehnung bleibt der Buffer ungebunden
- `UpdateDescriptorSets`: Count null, doppelte Writes desselben Slots, `descriptor_type = 0` und nicht zugewiesene Descriptor-Typ-Werte ergeben `BadValue`; Payload-Längenfehler `BadLength`; registrierter, aber zum Binding inkompatibler Descriptor-Typ sowie inkompatible Ressourcen ergeben `BadMatch`; Pending-Use ergibt `INVALID_SYNCHRONIZATION_STATE`; bei Ablehnung keine Teiländerung
- Erfolgreiches `UpdateDescriptorSets` aktualisiert atomar die Descriptor-Slots und indirekten Buffer-Referenzen aller nicht-pending Command Buffer, die die betroffenen Sets referenzieren; ein `EXECUTABLE`-Command-Buffer verwendet bei späterer Submission die aktuellen Set-Inhalte und wird durch das Update allein nicht invalidiert.
- Wird ein alter Buffer nach erfolgreichem Descriptor-Update zerstört, darf ein Command Buffer nicht allein wegen der durch das Update entfernten indirekten Referenz invalidiert werden; bleibt ein Descriptor-Slot auf einen zerstörten Buffer gerichtet, bleibt das Set nicht submitbar, bis der Slot korrigiert oder das Set freigegeben wurde.
- `ResetFence` prüft exakt 16 Bytes und Device-/Fence-XIDs vor dem Zustandscheck; unbekannte XIDs ergeben `BadValue`, falsche live Typen/Ownership/Cross-Device `BadMatch`, verlorenes Device `DEVICE_LOST`; nur `SIGNALED` und `FAILED` dürfen zurückgesetzt werden; andere Zustände ergeben `INVALID_SYNCHRONIZATION_STATE`, verlorenes Device `DEVICE_LOST`, Ablehnung erhält den Zustand
- Unbekannte/nicht-live XAverius-XIDs ergeben `BadValue`, falsche live Ressourcentypen und Cross-Client-/Cross-Device-Ownership `BadMatch`, ungültige Atoms `BadAtom` und belegte Create-XIDs `BadIDChoice`; dies gilt auch für `DestroyResource`, `BindBufferMemory`, `UpdateDescriptorSets`, `QueueSubmit` und `ResetFence`
- Memory-Alignment und Memory-Type-Kompatibilität
- Command-Buffer-Zustandsübergänge
- Fence- und Semaphore-Zustände sowie Timeouts
- Descriptor-Update/Freigabe während Pending-Use
- Ressourcenzerstörung bei internen Referenzen
- `DestroyResource` akzeptiert nur Buffer, Shader Module, Descriptor Set Layout, Pipeline Layout und Pipeline; es weist Fence, Semaphore, Device, Pools, Command Buffer, Descriptor Set und Memory mit `BadMatch` ab. Fence und Semaphore werden ausschließlich über `DestroyFence` beziehungsweise `DestroySemaphore` zerstört
- `DestroyResource` hat exakt 12 Bytes und inferiert Device/Ownership aus der Ressource; fremde Ownership und abgewiesene Recording-/Pending-Zustände ändern keine XID oder Referenz
- Erfolgreiches `DestroyResource` invalidiert die öffentliche XID sofort, erhält interne Objekte aber bis zum Ende notwendiger Referenzen und Backend-Zugriffe
- Destroy einer von einem `RECORDING`-Command-Buffer referenzierten Ressource wird atomar abgewiesen.
- Destroy einer von einem nicht-pending `EXECUTABLE`-Command-Buffer referenzierten Ressource invalidiert diesen Command Buffer.
- `FreeDescriptorSets` weist die Freigabe atomar mit `INVALID_SYNCHRONIZATION_STATE` ab, wenn ein ausgewähltes Set pending verwendet oder von einem `RECORDING`-Command-Buffer referenziert wird; bei Erfolg werden nicht-pending `EXECUTABLE`-Command-Buffer mit dieser Set-Referenz `INVALID`.
- `DestroyResource` auf Pipeline oder Pipeline Layout weist Recording-Referenzen und angenommene Pending-Use atomar ab; bei Erfolg werden referenzierende nicht-pending `EXECUTABLE`-Command-Buffer `INVALID`.
- `DestroyCommandPool`, `DestroyDescriptorPool` und `FreeDescriptorSets` werden bei verbotener Pending-/Recording-Referenz atomar abgewiesen; erfolgreiche Kaskaden invalidieren alle betroffenen XIDs. Device Loss allein blockiert `DestroyCommandPool` und `DestroyDescriptorPool` nicht: terminalisierte Pending-Arbeit bleibt kein Hindernis, aber Recording-Referenzen blockieren `DestroyDescriptorPool` weiterhin, bis der betreffende Command Pool zerstört wurde. `FreeDescriptorSets` prüft Ownership, aber blockiert die logische Freigabe nicht allein wegen Device Loss; bei Ablehnung darf keine Teilfreigabe stattfinden.
- `DestroyDescriptorPool` hat exakt 16 Bytes; es invalidiert Pool und Kind-Sets atomar und setzt referenzierende nicht-pending `EXECUTABLE`-Command-Buffer auf `INVALID`.
- `DestroyResource` auf einen Buffer wird während Pending-Use abgewiesen; nach erfolgreicher Zerstörung verhindern stale Descriptor-Slots eine neue Submission, bis sie aktualisiert oder freigegeben werden.
- `FreeMemory` ist ein eigener Void-Request mit exakt 16 Bytes; bei gebundenem Buffer ergibt er `BadMatch`; bei pending GPU-Zugriff `INVALID_SYNCHRONIZATION_STATE`; bei Ablehnung bleibt die Memory-XID live und die Allokation unverändert.
- Device Loss macht alle angenommenen nicht-terminalen Submissions fehlgeschlagen, setzt zugehörige Fences auf `FAILED`, invalidiert betroffene Command Buffer nach der Pending-Phase und erzeugt keine erfolgreiche Completion. Device Loss allein invalidiert keine öffentlichen Device-/Ressourcen-XIDs; Statusabfragen wie `GetFenceStatus` bleiben gemäß Request-Vertrag möglich, bis `DestroyDevice` oder Client-Disconnect die öffentliche Kaskadeninvalidierung auslöst.
- Einzelne Destroy-/Free-Requests werden nach Device Loss nicht pauschal mit `DEVICE_LOST` abgewiesen: ihre normalen Ownership-/Recording-/Lebensdauerprüfungen entscheiden. Terminalisierte Submissions und Host-Waits blockieren nicht allein wegen ihres früheren Pending-Zustands; `FreeMemory` bleibt verboten, solange ein intern lebender Buffer gebunden ist oder Backend-Zugriffe nicht sicher beendet sind.
- Wenn Backend-Quieszenz nach Device Loss nicht nachweisbar ist, werden interne Ressourcen quarantänisiert und weder freigegeben noch wiederverwendet, bis Quieszenz nachgewiesen oder der Serverprozess beendet ist.
- XID-Wiederverwendung bei ausstehender Arbeit
- Device Removal und Device Loss
- Korrekte XGE-Längen und Event-Feldpositionen
- Die XAverius-Major-Opcode wird pro X11-Server mit `QueryExtension` entdeckt, liegt im X11-Erweiterungsbereich 128–255 und wird sowohl als Request-`reqType` als auch als XGE-`extension` verwendet; `evtype` bleibt die statische Event-Type-ID. XGE-Headerlängen, feste Event-Gesamtlängen, reservierte Header-/Payload-Felder und registrierte Event-lokale Werte werden unabhängig validiert.
- Keine verspäteten X11-Fehler für angenommene asynchrone Requests
- Ein terminaler interner Submission-Ausgang auch dann, wenn das zugehörige Event nicht ausgewählt ist; bei ausgewähltem Event genau eine Zustellung des passenden Completion- oder Failure-Events
- `SUBMISSION_COMPLETE` und `SUBMISSION_FAILED` übernehmen den nicht-nulligen, verbindungsweit eindeutigen `submission_token` sowie exakt die Queue-Family- und Queue-Indizes der angenommenen `QueueSubmit`-Anforderung; für dieselbe Submission tritt nur ein terminaler Ausgang ein
- Nach `DestroyDevice` werden keine neuen Events mit der zerstörten Device-XID erzeugt oder zugestellt, auch wenn `ASYNC_ERROR` und `DEVICE_LOST` sonst nicht maskierbar sind; vorher in den X11-Ausgabestrom eingereihte Events bleiben unberührt
- Erfolgreiches `WriteBuffer` wartet auf alle zuvor angenommenen Submissions desselben logischen Devices, bevor es den Zielbereich verändert; dies gilt auch bei früherer Arbeit auf einer anderen Queue und bei überlappenden Buffer-Bereichen
- Jede nach erfolgreichem `WriteBuffer` angenommene Submission auf jeder Queue desselben logischen Devices sieht die hochgeladenen Bytes, ohne clientseitige Semaphore oder Barrieren allein für diese Sichtbarkeit
- Ein vorheriger fehlgeschlagener Submission-Ausgang verhindert `WriteBuffer` nicht, sofern das Device weiter verwendbar ist; der Upload erfolgt danach und spätere Submissions sehen die neuen Bytes
- Bei Device Loss oder fehlgeschlagenem Transfer sendet `WriteBuffer` keinen erfolgreichen Reply
- Ein früherer QueueSubmit wartet auf ein Timeline-Signal, das erst durch einen späteren `SignalSemaphore`-Request derselben Verbindung geliefert wird: `WriteBuffer` darf den Dispatcher nicht deadlocken; das Signal wird ausgeführt, die frühere Submission kann terminal werden, und spätere `QueueSubmit`-Requests passieren die Upload-Grenze erst nach erfolgreichem Reply
- `WriteBuffer` auf einem logischen Device erzeugt keine implizite Synchronisation mit einem anderen logischen Device auf derselben physischen GPU
- `ReadBuffer` wartet auf alle zuvor angenommenen Submissions desselben logischen Devices und auf relevante vorherige `WriteBuffer`-Transfers
- Readback-Ergebnisse werden nicht als korrekt vorausgesetzt, wenn fehlgeschlagene frühere GPU-Arbeit den gelesenen Bereich hätte verändern können
- Korrekte Berechnung von `C[i] = A[i] + B[i]`

- SelectEvents uses subopcode 40 and an exact total length of 32 bytes.
- SelectEvents rejects unknown scope values, reserved nonzero fields, unsupported mask bits, and inconsistent scope fields; rejection preserves the previous selection.
- A zero event mask clears only the selected scope; unmaskable ASYNC_ERROR and DEVICE_LOST delivery is independent of the selection.

- SelectEvents CONNECTION requires all target fields to be zero; DEVICE requires zero queue indices; QUEUE identifies a requested queue by device XID and family/index tuple.
- SelectEvents rejects a queue tuple that does not identify a requested queue, and rejects resources owned by another client without changing the previous mask.
- A closed client connection or failed event send does not prevent an accepted submission from reaching its internal terminal state or releasing safe backend resources.

- CreateDevice, CreateDefaultDevice, and SelectEvents before successful GEQueryVersion negotiation are rejected with BadMatch; no target XID or event-mask change is left behind.
- After XGE 1.0 negotiation, long XAverius XGE events are framed with GenericEvent (35), the XAverius major opcode in extension, and the registered CARD16 evtype.
- Property UUID byte preservation: a server returns the exact 16 bytes supplied by Vulkan for `deviceUUID` and `driverUUID`, without integer reinterpretation or host-endian conversion.
- Extension-name syntax: empty names, names longer than 255 bytes, non-ASCII bytes, embedded NUL bytes, and names that do not match the required Vulkan extension-name form are rejected with `BadValue` before registry lookup; syntactically valid names absent from the v0.1 registry produce `BadMatch`.
- `CreateDevice` validation order: malformed packet structure and reserved fields are rejected before resource lookup; feature and extension records are checked for syntax, duplicates, registry membership, and Physical Device support before any logical Device or backend object is published.
- `GetPhysicalDeviceProperty` successful replies use the exact registry type and length; UUID properties contain exactly 16 opaque bytes, `maxWorkGroupInvocations` exactly one `CARD32`, and `maxWorkGroupSize` exactly three `CARD32` values; all padding is zero.
- Feature-ID and device-extension registries are empty in v0.1: every feature ID is `BadValue`; malformed extension names are `BadValue`; any syntactically valid extension name is `BadMatch`; failures leave `device_xid` unallocated.
- Extension-name syntax tests include mixed-case extension suffixes (for example `VK_EXT_shaderObject`) and preserve the exact spelling; the syntax check must not incorrectly require the suffix to be lowercase.
- `spec/errors.md` is checked against all 40 assigned request subopcodes: every request uses the common framing/XID/ownership/atomicity rules where applicable, with request-specific length, value, state, backend, and synchronous-versus-asynchronous outcomes taking precedence when explicitly defined.
- Error precedence tests verify malformed length/record structure before field validation, field validation before XID resolution, and XID/type/ownership validation before state/backend checks; no rejected Void request leaves a partial resource or state change.

## Queue-Reihenfolge und Fortschritt

- Submissions derselben Queue werden in der Annahmereihenfolge eingereiht; unabhängige Arbeit darf sich überlappen.
- Zwischen verschiedenen Queues besteht ohne explizite Synchronisation keine zugesicherte Reihenfolge oder Memory-Visibility.
- Queueübergreifende Abhängigkeiten werden mit Semaphore-Signal und -Wait hergestellt. Erforderliche Memory-Dependencies werden separat nach Vulkan-Regeln geprüft.
- Fence-Waits und Host-Semaphore-Waits beobachten Zustände, erzeugen aber selbst keine Queue-seitige Abhängigkeit.
- Ein Host-Signal kann einen Queue-Wait auf denselben Semaphore-Wert freigeben, ordnet aber keine unverbundene GPU-Arbeit.
- Submission-Tokens und Event-Sequence-Nummern sind keine Ordnungswerte.
- Für unabhängige Queues sind weder Fairness noch eine feste maximale Scheduling-Latenz zugesichert.

## XGE- und Reply-ABI

- Jeder XAverius-XGE-Event-Header ist genau 32 Bytes groß: `response_type = 35`, `extension` ist der ausgehandelte XAverius-Major-Opcode, `sequence` liegt bei Offset 2, `length` bei Offset 4 und `evtype` bei Offset 8; Header-Padding bei Offset 10–31 ist null.
- XGE-Längen werden als `32 + 4 * length` geprüft: `ASYNC_ERROR` 60 Bytes/length 7; `DEVICE_LOST`, `DEVICE_STATUS_CHANGED`, `DEVICE_MEMORY_PRESSURE` und `DEVICE_IDLE` je 48 Bytes/length 4; `SUBMISSION_COMPLETE` und `SUBMISSION_FAILED` je 56 Bytes/length 6.
- Event-`evtype`-Werte stimmen exakt mit der Event-Registry überein (0–6); der dynamische Extension-Major-Opcode wird nicht als Event-Type-ID verwendet.
- Die event-spezifischen Felder beginnen bei Offset 32. Alle als reserviert definierten Felder sind null; `SUBMISSION_COMPLETE` und `SUBMISSION_FAILED` unterscheiden sich bei Offset 44 (reserviert null bzw. `failure_class`) und dürfen für dieselbe angenommene Submission nicht beide als terminales Event auftreten.
- `SelectEvents` hat exakt 32 Bytes, ist als Void-Request unter Subopcode 40 registriert und besitzt null Flags (Offset 5) sowie ein null-reserviertes Common-Header-Feld (Offset 6). Die Scope-spezifischen Felder liegen bei Offset 8–31; der Prüfer kontrolliert Layout und Registrierung gemeinsam. Der Event-Maskenwert wird anhand des Scopes validiert; Fehler ändern die vorherige Auswahl nicht.
- Feste Replies sind 32 Bytes mit `reply.length = 0`, sofern keine Payload über Offset 32 hinausgeht. Bei variabler Payload bezeichnet `reply.length` ausschließlich die gepaddeten Vierbyteeinheiten nach Offset 32; Payload-Bytes und Null-Padding werden getrennt geprüft.
- `GetFenceStatus` legt den Fence-Status in Reply-Byte 1 ab; Offset 0 bleibt `response_type`, Offsets 2–3 Sequenznummer und Offsets 4–7 `reply.length = 0`. Die restlichen XAverius-reservierten Bytes sind null.

## Automatisierter Wire-Layout-Check

Im Repository-Root ausführen:

```sh
python3 -m py_compile tools/check-wire-layout.py
python3 tools/check-wire-layout.py
```

Der Checker verwendet nur die Python-Standardbibliothek. Er prüft die sieben registrierten XGE-Event-IDs und -Längen, extrahiert die Event-Felder aus den Layoutbeschreibungen und meldet Überlappungen, Lücken, unzulässige Offsets/Ausrichtung, Felder außerhalb der Eventlänge sowie nicht explizit auf null gesetzte reservierte Felder. Für Replies vergleicht er das 40-Request-Inventar und die Längenmatrix mit dem Subopcode-Register und prüft zentrale feste Reply-Felder sowie variable `reply.length`-Formeln in den normativen Kapiteln. GitHub Actions führt den Check bei Änderungen auf dem Arbeitsbranch und bei Pull Requests aus.

Der Check ist eine statische Dokumentations-Konsistenzprüfung. Er ersetzt weder Tests gegen einen laufenden X11/XGE-Server noch Backend-/Vulkan-Konformitätstests.

### Reply-ABI-Abdeckung des statischen Prüfers

Der Wire-Layout-Check muss alle elf als `Reply` registrierten Requests abdecken: `EnumeratePhysicalDevices`, `GetPhysicalDeviceProperty`, `GetPhysicalDeviceQueueFamilyProperties`, `GetPhysicalDeviceMemoryProperties`, `GetBufferMemoryRequirements`, `WriteBuffer`, `ReadBuffer`, `GetSemaphoreCounterValue`, `WaitSemaphores`, `GetFenceStatus` und `WaitForFence`. Die Prüfliste wird mit den `Reply`-Einträgen im zentralen Subopcode-Register verglichen; fehlt ein registrierter Reply oder ein erwarteter Vertrag, schlägt der Check fehl.

Die XGE-Prüfungen validieren außerdem die gemeinsamen 32-Byte-Headerfelder und deren Offsets, den dynamischen Extension-Major-Opcode gegenüber den statischen Event-Type-IDs, die exakten Payload-Feldtypen/-Offsets und Längen aller sieben registrierten Events, die event-lokalen Werte-Registries sowie die 32-Byte-`SelectEvents`-Struktur einschließlich Scope-abhängiger Masken und XGE-Aushandlungsregeln. Synthetische Frames für Little- und Big-Endian prüfen die Längenformel und weisen inkonsistente Längen, falsche `response_type`-Werte und nicht-nullige reservierte Headerbytes zurück. Diese Tests sind statische ABI-/Referenzprüfungen und ersetzen keinen Test gegen einen laufenden X11/XGE-Server.

Zusätzlich zu festen Reply-Feldern prüft er jetzt die variablen Record- und Payload-Verträge: `PHYSICALDEVICEINFO`-Records einschließlich Namenslänge und Padding, `QUEUEFAMILYINFO`-Records, `MEMORYTYPEINFO`/`MEMORYHEAPINFO`-Größen und -Counts, Property-Werte, `ReadBuffer`-Payloads sowie den variablen Request-/Reply-Vertrag von `WriteBuffer` und `WaitSemaphores`. Der Check ist absichtlich eine normative Text-Konsistenzprüfung; er führt keine Server- oder Vulkan-Operation aus.

Die Formeltests enthalten zusätzlich Grenzwertvektoren für Byte-Padding und Reply-Wörter bei Payload-Längen 0, 1, 3, 4 und 5; für `PHYSICALDEVICEINFO`-Namenslängen 0, 1, 4 und 5; für leere und nichtleere Queue-Family-Arrays; sowie für Memory-Type-/Heap-Counts einschließlich der v0.1-Maxima 32/16. Für `WriteBuffer` und `WaitSemaphores` werden variable Request-Längen ebenfalls anhand konkreter Count-/Payload-Vektoren geprüft.

## Golden-Wire-Testvektoren

`tests/wire-vectors.json` enthält konkrete Request-Bytes für `CreateBuffer`, `WriteBuffer` und `ReadBuffer`, jeweils in Little- und Big-Endian-Byteordnung. Die `WriteBuffer`-Vektoren decken Payload-Längen 1, 3, 4 und 5 Bytes ab und prüfen damit Padding von 3, 1, 0 und 3 Bytes. Die Fixtures prüfen den 8-Byte-Request-Header, das Null-`data`-Feld, den Subopcode am Offset 4, die vierbytebasierte Request-Länge und die festen Feldlayouts. Zusätzliche Raw-Frame-Tests weisen abgeschnittene Header, falsche deklarierte Längen und nicht-nullige reservierte Headerbytes zurück. Der Major-Opcode `0x90` ist nur ein Fixture-Wert; im Betrieb wird er vom X-Server zugewiesen.

Mit `python3 -m unittest discover -s tests -p 'test_*.py' -v` werden die Golden-Bytes gegen einen kleinen Referenz-Encoder geprüft. Der Referenz-Encoder ist kein XAverius-Client und keine Serverimplementierung: Die Tests belegen die Konsistenz der Vektoren und der abgedeckten Wire-Regeln, nicht die Interoperabilität. Sobald ein Client- oder Server-Encoder existiert, muss derselbe Vektorsatz direkt gegen dessen erzeugte beziehungsweise geparste Bytes laufen. Die Negativtests weisen außerdem abweichende deklarierte Paketlängen, nicht-nulliges WriteBuffer-Padding, inkonsistente Payload-Längen und nicht-nullige reservierte CreateBuffer-Felder zurück. Diese Tests prüfen die Ablehnungslogik des Referenz-Encoders; sie sind ausdrücklich noch kein Nachweis, dass ein Server dieselben fehlerhaften Pakete korrekt zurückweist.


# Presentation-profile conformance cases (future profile)

The following cases apply only when the server implements the presentation-capable profile; they do not expand the compute-only baseline by implication.

- Surface creation binds the exact internal identity of an existing X11 Window. Unknown/non-Window IDs fail synchronously, a failed create leaves the target XID unallocated, and destroying/reusing the numeric Window XID never retargets an existing Surface.
- Surface is connection-owned and can be queried against more than one logical Device. A Surface destroy with a live Swapchain reference is rejected atomically. Device destruction invalidates device-owned Swapchains but does not implicitly destroy the connection-owned Surface.
- A Swapchain image is identified only by (Swapchain XID, image_index), has no independent XID, and cannot be acquired twice concurrently. Invalid indices and invalid image-state transitions leave state unchanged.
- Capability query returns a self-consistent variable-length reply: exact total size is 64 + 8 * format_pair_count + 4 * present_mode_count + 8 * queue_family_count; reply.length is 8 + 2 * format_pair_count + present_mode_count + 2 * queue_family_count. Count arithmetic must be overflow-checked. Queue-family support records contain exactly one ascending-index record per physical queue family. A zero-sized window reports TEMPORARILY_NOT_PRESENTABLE without blocking.
- CreateSwapchain either creates exactly the requested image_count and returns that count, or leaves the target XID unallocated. Unreported format/color-space pairs, modes, and usage bits are rejected atomically.
- `AcquireNextImage` with `timeout_ns = 0` returns `NOT_READY` when no image is immediately available; expiration of a finite positive timeout returns `TIMEOUT`. Every non-success reply has `image_index = 0`; no failure signals the optional semaphore/fence or changes image state. Semaphore and fence are independently optional and may both be supplied; on SUCCESS each supplied eligible same-device object is signaled exactly once. A successful acquire returns a valid image index; timeline semaphore acquisition signals are rejected.
- QueuePresent rejection leaves the image ACQUIRED and does not consume wait semaphores. An accepted present moves the image to PRESENT_PENDING; request success does not imply GPU completion, image release, or presentation completion.
- QueuePresent reserves each binary wait atomically with acceptance and uses the same one-pending-wait rule as QueueSubmit. Acceptance does not consume the signal; a confirmed backend wait does. If an accepted present fails before wait completion, each semaphore preserves confirmed unconsumed state, records confirmed consumption, or becomes UNTRUSTED if payload outcome is uncertain. UNTRUSTED waits fail with DEPENDENCY_FAILED; incompatible pending waits fail atomically with INVALID_SYNCHRONIZATION_STATE.
- IMAGE_RELEASED and PRESENTATION_COMPLETE are distinct milestones and may arrive in either order. Each accepted present has one internal terminal presentation transition and one internal image-release-or-invalidation transition. PRESENTATION_COMPLETE is enqueued only if Queue mask bit 3 is set at its terminal point and connection/device lifecycle permit delivery. IMAGE_RELEASED is enqueued only if the image is reusable, Queue mask bit 2 is set at its release point, and connection/device lifecycle permit delivery. Masking or suppressed delivery never skips internal cleanup. If the image is invalidated, no IMAGE_RELEASED is enqueued. No new events are enqueued after DestroyDevice for that Device; previously enqueued events remain unaffected. Disconnect suppresses delivery without skipping internal terminal cleanup. An image is reacquirable only after internal release; the event is visible only under its delivery conditions.
- Each presentation event's Queue mask is sampled independently at its own terminal milestone (image-release eligibility versus presentation completion); later `SelectEvents` changes cannot retroactively change that event's delivery decision.
- Resize marks the old Swapchain OUT_OF_DATE, prevents new acquire/present acceptance, and allows replacement creation while old work drains. Window destruction marks the Surface SURFACE_LOST; no XID reuse can revive it.
- Accepted-present terminalization is serialized exactly once: resize permits `SUCCESS` only if the accepted operation still reaches its completion point, otherwise `OUT_OF_DATE`; a destroyed Window yields `SURFACE_LOST` for still-pending operations that cannot complete, and Device Loss yields `DEVICE_LOST`. These lifecycle failures invalidate the affected image/Swapchain and do not emit `IMAGE_RELEASED`; a later lifecycle notification cannot overwrite an already serialized terminal result.
- `PRESENTATION_FAILED` emits `IMAGE_RELEASED` only after backend quiescence is established and the image remains reusable in a usable Swapchain; otherwise the image/Swapchain is invalidated. Internal cleanup completes exactly once even when event delivery is suppressed.
- Conformance validation must check presentation event IDs 7 and 8 with total lengths 64 and 64 bytes respectively, and queue event-mask bits 2 and 3 are rejected by compute-only implementations.


## Presentation-profile conformance cases (provisional)

The following cases apply only when the presentation-capable profile is advertised; they do not expand the compute-only baseline:

- `CreateSurface` rejects a bad target XID with `BadIDChoice`, an invalid/non-Window core X11 Window XID with `BadWindow`, and a live Window owned by another X11 client with `BadMatch`; failure allocates no Surface and retains no window reference.
- Mixed-failure `CreateSwapchain` requests validate scalar fields first, then `device_xid`, target `swapchain_xid`, and `surface_xid` in wire-field order; capability/status checks occur only after XID, type, ownership, and Device-state validation.
- `DestroySurface` is atomically rejected with `INVALID_SYNCHRONIZATION_STATE` while any live Swapchain references it.
- `DestroySwapchain` is atomically rejected with `INVALID_SYNCHRONIZATION_STATE` while a recording command buffer, pending acquire, accepted queue work, accepted presentation, or possible backend access still references its images; acquired-but-idle images alone do not block destruction. The resource-lifetime matrix must state the same rule.
- `GetSurfaceCapabilities` uses exactly the defined 64-byte fixed reply prefix plus 8 bytes per format/color-space pair, 4 bytes per present mode, and 8 bytes per queue-family support record; `reply.length = 8 + 2 * format_pair_count + present_mode_count + 2 * queue_family_count`. Every physical queue family has exactly one ordered support record. Temporary-not-presentable, surface-lost, and device-lost statuses return zeroed capability fields as specified.
- `CreateSwapchain` validates image count and extent bounds, a reported format/color-space pair, a reported mode, and advertised usage bits against current capabilities. A zero-sized Surface or requested extent outside current supported bounds returns `OUT_OF_DATE`; a valid but unsupported configuration returns `UNSUPPORTED_CONFIGURATION`. Success provides the exact requested image count; every non-success reply sets `actual_image_count = 0` and leaves the target Swapchain XID unallocated.
- `AcquireNextImage` timeout, not-ready, out-of-date, surface-lost, device-lost, and device-destroyed results neither signal the supplied semaphore/fence nor change image state. `DestroyDevice` terminates an open acquire with `DEVICE_DESTROYED` without waiting for image availability; an already serialized terminal result wins. Disconnect suppresses the reply but removes the registration and releases registration-only references safely. Destroying the referenced Swapchain or Surface while the acquire is pending remains rejected.
- `QueuePresent` has total request size `40 + 4 * wait_semaphore_count` and a 36-byte reply with status values 0 `SUCCESS`, 1 `OUT_OF_DATE`, 2 `SURFACE_LOST`, and 3 `DEVICE_LOST` (local to the reply field). Duplicate waits, token zero/reuse, wrong resource types, invalid image state, and non-existent queues follow the specific error mapping; rejection does not consume waits or transition the image.
- A successful `QueuePresent` reply means accepted, not displayed. Image release and presentation completion are separate terminal events and may be observed in either order; each accepted presentation gets at most one of each event.

- Presentation error precedence is tested with mixed-failure requests: malformed length/overflow beats all field checks; invalid scalar syntax (including zero token or duplicate waits, but not reuse of an accepted token) beats XID resolution; XIDs are resolved in wire-field order; live type/ownership errors beat Device and lifecycle outcomes; Device loss beats Surface loss and accepted-token reuse; Surface loss and OUT_OF_DATE beat accepted-token reuse; unsupported queue presentation capability is `BadMatch` before token reuse; accepted-token reuse returns `BadValue` before image-state and semaphore-eligibility checks. The expected winner is the first failing stage, and every rejected request leaves all state unchanged.
- `CreateSurface` validates the target create-XID before the Window XID; `CreateSwapchain` validates `device_xid`, target `swapchain_xid`, then `surface_xid` after scalar syntax. Failed creates leave target XIDs unallocated and retain no references.
- `GetSurfaceCapabilities` returns `DEVICE_LOST` rather than `SURFACE_LOST` when both apply; each non-success status has zero capability fields and arrays and a fixed 64-byte reply (`reply.length = 8`).
- `CreateSwapchain` returns `DEVICE_LOST` before `SURFACE_LOST`, `SURFACE_LOST` before `OUT_OF_DATE`, and `OUT_OF_DATE` before `UNSUPPORTED_CONFIGURATION`. Every non-success reply has `actual_image_count = 0` and leaves the target XID unallocated.
- `AcquireNextImage` lifecycle outcomes precede timeout polling: `DEVICE_LOST`, then `SURFACE_LOST`, then `OUT_OF_DATE`; `NOT_READY` is only the zero-timeout result for a usable Swapchain with no immediately available image, and `TIMEOUT` is only returned when a finite timeout expires. `DEVICE_DESTROYED` applies only to a pending acquire terminalized by `DestroyDevice`, with the first serialized terminal result winning. Every non-success result has zero `image_index` and signals neither optional synchronization object.
- `QueuePresent` returns `DEVICE_LOST` after valid XIDs/types/ownership but before queue/index validity; once the Device is usable, nonexistent queue-family/index or out-of-range image index is `BadValue`, then `SURFACE_LOST` precedes `OUT_OF_DATE`, and both lifecycle statuses precede image/semaphore state checks.
- After `QueuePresent` lifecycle status checks, image state is validated before wait semaphores; if the image is `ACQUIRED`, wait semaphores are checked in array order. An `UNTRUSTED` wait yields `DEPENDENCY_FAILED`; another incompatible semaphore state or pending wait yields `INVALID_SYNCHRONIZATION_STATE`. Zero token, duplicate wait XIDs, and accepted-token reuse are `BadValue`; tokens from rejected attempts remain reusable. Acceptance atomically reserves the token and all wait slots and changes `ACQUIRED` to `PRESENT_PENDING`; any rejection leaves pre-request image/semaphore states unchanged and does not restore an image invalidated by an independent lifecycle transition.
- A buffer-to-swapchain-image command requires an acquired image at submission acceptance, retains the exact Swapchain/image identity while pending, and prevents backing storage from being freed until the submission and backend accesses are terminal.
- If `QueueSubmit` is accepted before `QueuePresent`, the submission keeps its exact image/Swapchain references and presentation requires the specified GPU semaphore dependency where the submission may access the image; a copy submission processed after the image has transitioned to `PRESENT_PENDING` is atomically rejected with `INVALID_SYNCHRONIZATION_STATE`. Request order alone is not a GPU dependency.
- Destroying a Buffer referenced by a `RECORDING` command buffer is atomically rejected with `INVALID_SYNCHRONIZATION_STATE`; successful Buffer destruction invalidates all non-pending executable command buffers that still reference it.
- The provisional copy entry rejects unknown Buffer/Swapchain XIDs with `BadValue`, wrong live types/ownership/device or incompatible transfer usage with `BadMatch`, malformed dimensions/alignment/out-of-range source spans and invalid image indices with `BadValue`, and a non-`ACQUIRED` image at submission acceptance with `INVALID_SYNCHRONIZATION_STATE`; every rejection is atomic.
- Resize/out-of-date, Window destruction/surface-lost, and device loss prevent new acquire/present operations while preserving safe terminal cleanup of previously accepted work. Accepted present operations reach a terminal status; a non-reusable image is invalidated rather than left PRESENT_PENDING.


## Request framing, maximum length, and BIG-REQUESTS

- XAverius v0.1 rejects BIG-REQUESTS framing: an XAverius request whose original X11 16-bit `length` field is zero is rejected as `BadLength` before offset 4 is interpreted as the XAverius common header.
- A normal request of exactly 262140 bytes is the maximum permitted size; a request that would exceed 262140 bytes is rejected with `BadLength`, even if its variable-length formula and counts are otherwise internally consistent.
- Variable-length request formulas are evaluated with checked arithmetic. Counts that overflow the formula, a computed size above 262140 bytes, a declared-length mismatch, or trailing/truncated payload bytes all produce `BadLength` before payload allocation, XID lookup, or state mutation.
- Chunked `WriteBuffer`, `ShaderModuleData`, and `CommandBufferData` requests enforce the limit per wire request. The aggregate logical upload/recording may exceed the limit only by using multiple valid chunks; a single oversized chunk is rejected.
- For each rejection above, no partial resource creation, upload commit, command-buffer append/finalization, queue-submission acceptance, or event-mask change occurs.

- Fehlerpräzedenz für mehrteilige Requests: Bei `BindBufferMemory` schlägt ein unbekanntes XID (`BadValue`) einen Device-Loss-Fehler; falscher live Typ/fremde Ownership (`BadMatch`) schlägt Device Loss; nach gültigen XIDs und Ownership schlägt `DEVICE_LOST` einen bereits gebundenen Buffer oder inkompatiblen Memory-Type. Bei `UpdateDescriptorSets` schlagen Länge/Feldsyntax und unbekannte XIDs Device-/Zustandsfehler; nach XID-/Typ-/Ownership-Prüfung schlägt `DEVICE_LOST` Layout-/Binding-Inkompatibilität und einen Pending-Set-Konflikt. Alle abgewiesenen Requests bleiben atomar und verändern keine Bindung, Descriptor-Slots oder internen Referenzen.

- Fehlerpräzedenz für Create-/Batch-Requests: `AllocateDescriptorSets` prüft zuerst Länge und Feldsyntax, dann Ziel-Set-XIDs in Array-Reihenfolge (`BadIDChoice`), dann Device-/Pool-/Layout-Eingabe-XIDs in Wire-Reihenfolge (`BadValue`), danach Typ/Ownership (`BadMatch`) und Device-Zustand (`DEVICE_LOST`/`DEVICE_UNAVAILABLE`) vor Pool-Kapazität und Backend-Allokation. `CreatePipelineLayout` und `CreateComputePipeline` prüfen Feldsyntax vor Ziel-XID, Ziel-XID vor Eingabe-XIDs, dann Typ/Ownership und Device-Zustand vor geräteabhängigen Kompatibilitäts- bzw. Backend-Prüfungen. Jeder Fehler lässt alle Ziel-XIDs unangelegt.

- `ResetFence`-Fehlerpräzedenz: falsche Länge schlägt alle weiteren Prüfungen; unbekannte Device-/Fence-XIDs ergeben `BadValue`, falscher live Typ/Ownership/Cross-Device `BadMatch`; nach gültigen XIDs und Ownership gewinnt `DEVICE_LOST` vor `INVALID_SYNCHRONIZATION_STATE` für einen nicht zurücksetzbaren Fence-Zustand. Jede Ablehnung erhält den gespeicherten Fence-Zustand.


## Presentation request wire-layout audit (provisional profile)

The request/reply framing matrix is cross-checked against [the presentation chapter](presentation.md#cross-request-wire-length-audit). Request sizes include the 8-byte X11/XAverius header; reply sizes include the 32-byte X11 reply header.

| Request | Request bytes | Normal reply bytes | Reply length field |
|---|---:|---:|---:|
| CreateSurface | 16 | none | — |
| DestroySurface | 12 | none | — |
| GetSurfaceCapabilities | 16 | 64 + variable records | 8 + 2×format_pair_count + present_mode_count + 2×queue_family_count |
| CreateSwapchain | 48 | 40 | 2 |
| DestroySwapchain | 12 | none | — |
| AcquireNextImage | 32 | 44 | 3 |
| QueuePresent | 40 + 4×wait_semaphore_count | 36 | 1 |

Conformance tests MUST verify every fixed request at exact length and at one four-byte unit shorter/longer, plus QueuePresent count/length mismatch and arithmetic overflow. Reply tests verify the X11 reply length field against the actual serialized byte count, zero reserved fields, and status-dependent fields. In particular, GetSurfaceCapabilities has a 64-byte minimum reply; each variable record contributes exactly the bytes specified in presentation.md. CreateSwapchain has a 48-byte request but a 40-byte reply; these lengths must not be conflated. AcquireNextImage's request is 32 bytes and its reply is 44 bytes. QueuePresent's request length varies with the semaphore count, but its reply is always 36 bytes.

For each request, mixed-failure tests verify framing before scalar syntax, scalar syntax before XID resolution, XID/type/ownership checks before lifecycle and mutable-state checks, and atomic rejection. CreateSurface and CreateSwapchain tests verify target-XID validation order and that failed creation leaves the target XID unallocated. QueuePresent tests verify that rejection neither consumes waits nor reserves the token nor transitions the image, while an accepted request commits token, wait reservations, references, and image transition together. Accepted asynchronous failure must produce one terminal presentation outcome and no delayed X11 request error.

Presentation lifecycle race tests MUST also cover the following serialized outcomes, not merely the request/reply bytes:

- Race `QueuePresent` acceptance against Surface loss, Swapchain resize/out-of-date, and Device loss. If the lifecycle transition is serialized before acceptance, return the specified normal status without reserving the token or wait slots; if acceptance is serialized first, preserve the accepted operation and terminalize it exactly once according to the first serialized terminal outcome.
- Race image release and presentation completion in both orders. Each accepted token may produce at most one `IMAGE_RELEASED` and at most one `PRESENTATION_COMPLETE`; masking either event must not skip its underlying state transition or resource cleanup.
- Fail a backend wait before it consumes a signal, after confirmed consumption, and with an uncertain consumption result. Verify semaphore state is respectively preserved, updated, or marked `UNTRUSTED` as specified, and ensure the image is released only if reuse is safe; otherwise invalidate the image/Swapchain rather than leaving `PRESENT_PENDING` indefinitely.
- Reuse a token after a rejected status reply and after a synchronous validation error (both permitted), then reuse it after an accepted presentation (must fail with `BadValue`). Verify that a status reply does not hide higher-priority malformed-wire, scalar, XID, Device, queue/index, or lifecycle errors.
- Destroy the Swapchain after an acquired-but-idle image, after accepted presentation work, and while backend access is possible. The first case may succeed once GPU references are drained; the latter cases must reject atomically until all relevant references and accesses are terminal.

These are state-machine conformance tests; golden-wire tests alone cannot establish them.
