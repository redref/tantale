[![Build Status](https://travis-ci.org/redref/tantale.svg?branch=master)](https://travis-ci.org/redref/tantale)
[![Coverage Status](https://coveralls.io/repos/github/redref/tantale/badge.svg?branch=master)](https://coveralls.io/github/redref/tantale?branch=master)

# Tantale

Tantale intend to be a monitoring tool (yet another nagios) built with simplicity, scaling and reuse in mind.

Unlike nagios, Tantale use a standard backend (NoSQL database) to store checks results. Then, you can query backend directly to interface with a lot more tools (logs, statistics, ...).

To know cons / drawbacks of tantale, you may read :
[Why tantale ?](docs/why-tantale.md)

## Components

Tantale contain 3 **independant** processes

### Livestatus

Provide a livestatus API to GUI's (adagios/check-mk-multisite) to query backend.

>Tested clients : check-mk-multisite, (more to come)

[Details on livestatus implement](docs/livestatus.md)

### Input

Socketline listener pushing checks into backend.

Input format:
```
<timestamp_s> <hostname> <check_name> <status> <plugin_output>|<comma_separated_contacts>
```

### Performance

On a single node (dev node), with basic configuration. Mainly IO bound.

```
Update 8000 checks to outdated in 7.094238 seconds.
Created 8000 checks in 7.103210 seconds.
```

### Client

Collect diamond metrics on hosts (with bundled diamond handler) and/or nagios checks from FIFO then forward them to Input.

  * Diamond : check value range for a metric

## How to build monitoring with Tantale ?

None of processes are mandatory. You may use only one of them. But, typical architecture:

  * Tantale client on all hosts
  * Some Tantale Input (you may use Haproxy setup to provide HA)
  * Some Tantale Livestatus (you may use Haproxy setup to provide HA)

## Inspirations

  * [Diamond](https://github.com/python-diamond/Diamond)
  * [Graphite - Carbon](https://github.com/graphite-project/carbon)
