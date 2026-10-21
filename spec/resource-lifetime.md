## Client-Ressourcen

Client-erzeugte XAverius-Ressourcen verwenden gültige, vom Client allokierbare XIDs.

Ein ungültiger oder bereits belegter Create-XID ergibt `BadIDChoice`, sofern der jeweilige Request keine speziellere X11-Regel vorschreibt.

Der Server muss für jede Ressource eine interne Identität verwalten, die nicht allein aus der öffentlichen XID besteht. Dadurch darf eine spätere Wiederverwendung derselben XID niemals laufende Arbeit auf eine neue Ressource umleiten.

Eine erfolgreich zerstörte öffentliche Ressource ist für neue Requests nicht mehr adressierbar.

# Ressourcenlebenszyklus und Zerstörung

## Zustandsmodell

Jedes Objekt besitzt mindestens zwei getrennte Lebensdaueransichten:

**Öffentlicher Zustand**

- `LIVE`
- `INVALID`

**Interner Zustand**

- `ACTIVE`
- `DESTROY_PENDING`
- `RELEASED`

Die Implementierung sollte zusätzlich die interne Ressourcenidentität, Client- und Device-Ownership, abhängige Objekte sowie ausstehende Submission-Referenzen verfolgen.

Die öffentliche XID wird bei erfolgreicher Zerstörung sofort ungültig. Die tatsächliche Vulkan-Zerstörung darf verzögert erfolgen.

## Ownership-Hierarchie

Explizite Eltern-Kind-Beziehungen:

- Device → alle device-eigenen öffentlichen Ressourcen
- CommandPool → zugehörige Command Buffer
- DescriptorPool → zugehörige Descriptor Sets

Andere Beziehungen sind Abhängigkeiten, keine automatischen Ownership-Beziehungen:

- Buffer ↔ Memory
- Pipeline ↔ Pipeline Layout
- Pipeline ↔ Shader Module während der Erstellung
- Pipeline Layout ↔ Descriptor Set Layout während der Erstellung
- Command Buffer ↔ Ressourcen, die in aufgezeichneten Commands verwendet werden

Die Implementierung darf nicht annehmen, dass jedes Objekt, dessen Handle beim Erstellen eines anderen Objekts verwendet wurde, dauerhaft existieren muss. Maßgeblich sind die tatsächlichen Vulkan-Lebensdauerregeln.

## Zerstörungsmatrix

| Ressource | Öffentliche Zerstörung | Regel bei ausstehender Verwendung |
|---|---|---|
| Device | Invalidiert Device und Kinder sofort | Interne Bereinigung wird verzögert |
| CommandPool | Invalidiert Pool und Kind-Command-Buffer | Abweisen, solange ein Kind pending ist |
| CommandBuffer | XID wird ungültig | Abweisen, solange pending |
| DescriptorPool | Invalidiert Pool und Kind-Sets | Abweisen, solange ein Kind-Set pending ist |
| DescriptorSet | XID wird ungültig | Abweisen, solange pending |
| Buffer | XID wird ungültig | Buffer und gebundener Speicher bleiben intern erhalten |
| Memory | XID wird ungültig | Tatsächliche Freigabe erst, wenn abhängige Objekte und Arbeit es erlauben |
| Pipeline | XID wird ungültig | Konservative Regel: Zerstörung bei Pending-Use abweisen |
| PipelineLayout | XID wird ungültig | Konservative Regel: Zerstörung bei noch bestehender Command-/Submission-Abhängigkeit abweisen |
| ShaderModule | Nach erfolgreicher Pipeline-Erstellung unabhängig zerstörbar | Vulkan-Lebensdauerregeln bleiben maßgeblich |
| DescriptorSetLayout | Nach erfolgreicher Pipeline-Layout-Erstellung unabhängig zerstörbar | Vulkan-Lebensdauerregeln bleiben maßgeblich |
| Fence | XID wird ungültig | Konservative Regel: Pending-Zerstörung abweisen |
| Semaphore | XID wird ungültig | Konservative Regel: Zerstörung bei Pending-Use abweisen |
| Physical Device | Nicht durch Client zerstörbar | Server-Ownership; XID wird nie neu zugewiesen |

Die Regeln sind XAverius-API-Entscheidungen und keine Behauptung, dass Vulkan für alle Ressourcentypen identische Lebensdauerbeschränkungen definiert.

## `DestroyResource`

Vorgeschlagener generischer Request:

- Offset 8: Ressourcen-XID
- Gesamtlänge: 12 Bytes

Die genaue Zulässigkeit für einzelne Ressourcentypen wird durch die jeweilige API-Regel bestimmt. Physical Devices sind ausgenommen.

Ein erfolgreicher Request invalidiert die öffentliche XID sofort. Interne Objekte dürfen erst freigegeben werden, wenn ihre Vulkan-Lebensdauerbedingungen erfüllt sind.

Ungültige XIDs, falsche Typen und fremde Ownership werden gemäß der request-spezifischen X11-Fehlerzuordnung behandelt.

## Device-Zerstörung und Client-Disconnect

Bei `DestroyDevice` oder Client-Disconnect werden öffentliche Device-Ressourcen ungültig.

Die interne Bereinigung muss sicher und unabhängig von der öffentlichen XID-Verfügbarkeit erfolgen. Der Server darf nicht unbegrenzt auf einem hängenden oder verlorenen Device warten.

Nach Device Loss müssen betroffene Operationen als fehlgeschlagen behandelt werden. Der Server darf nicht so tun, als sei GPU-Arbeit erfolgreich abgeschlossen worden.

## Command Buffer und Descriptor Sets

Ein pending Command Buffer darf in v0.1 nicht verändert, zurückgesetzt, freigegeben oder erneut eingereicht werden.

Ein Descriptor Set darf nicht aktualisiert oder freigegeben werden, solange eine angenommene Submission es verwenden kann.

Update-after-bind und Update-unused-while-pending werden nicht angeboten.

## Buffer und Memory

Ein Buffer darf öffentlich invalidiert werden, obwohl eine Submission ihn noch benötigt. Das interne Buffer-Objekt und gebundener Speicher müssen erhalten bleiben, bis Vulkan ihre Freigabe erlaubt.

Memory darf nicht freigegeben werden, solange ein gebundener Buffer oder eine ausstehende Operation darauf angewiesen ist.

## Fehler bei ungültigen Lebenszyklusoperationen

- Ungültige oder zerstörte XID: request-spezifischer Standard-X11-Fehler
- Falscher Typ oder inkompatible Ressource: normalerweise `BadMatch`
- Falsches Device: `BadMatch`
- Zerstörung eines pending Command Buffers oder Descriptor Sets: `INVALID_SYNCHRONIZATION_STATE`
- Ungültiger Fence-Reset: `INVALID_SYNCHRONIZATION_STATE`
- Verlorenes Device: `DEVICE_LOST`, sofern der Request nicht ausdrücklich noch die logische Invalidierung erlaubt

Die erfolgreiche Device-Kaskadeninvalidierung ist eine Sonderregel und wird nicht durch die normalen Pending-Use-Ablehnungen blockiert.
