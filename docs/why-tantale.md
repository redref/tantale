# Why Tantale ?

By experience, it can be difficult to query or interface monitoring with other tools on classis setup (Nagios, OMD, Check_mk). 

I was searching a solution to make correlation analysis on systems problems (frequency, duration, ...).

## Objectives

  * Provide a Livestatus API over non monitoring specific tools.
  * Scaling easily
  * Rely on common used tools (diamond, elasticsearch, ...) to be interoperable

## Assumptions

### Configuration data is already present on hosts

Your configuration management already carry everything to the host.

Tantale carry configuration regarding data (checks, contacts, ...) **only** on Client process.

### Livestatus API is rich, but sometimes not used

Perfdata are called metrics today. Indeed, tantale does not store nor display them.

Tantale provide Livestatus API, but some functionnalities may differ from classic implementations (like downtimes, commands, ...).
[Details on livestatus implement](livestatus.md)

### Passive checks

## Cons

### Stats and graphs on monitoring results and events

Cf. backend tools - grafana / kibana

### No daemon restart

On large setup, restart of monitoring daemons can take a really long time. Tantale does not need it at all.

### Replication / High availability

NoSQL backend natively handle replication and high availability.

Tantale does not handle sessions nor connection state dependance. HA can easily be provided by an HAproxy setup.

### Simple

Quite no configuration.

## Drawbacks

### Tiny project

### Miss some functionalities from Livestatus

### New and not production ready



