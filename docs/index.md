[![Build Status](https://travis-ci.org/redref/tantale.svg?branch=master)](https://travis-ci.org/redref/tantale) [![Coverage Status](https://coveralls.io/repos/github/redref/tantale/badge.svg?branch=master)](https://coveralls.io/github/redref/tantale?branch=master)

# Tantale

Tantale intend to be a monitoring tool which interact with third party monitoring GUI's and tools.

Assumptions:
  * configuration already on configuration-management tools
  * livestatus schema is quite complicated (and never used ?)
  * mainly passive checks

Tantale store all checks/statuses (hosts/services/...) into database backend (only elasticsearch for now) in order to by fully interoperable.

Objective is to provide a Livestatus API keeping interoperability in mind.

Some cons:
  * get monitoring events onto grafana/kibana
  * no nagios/shinken daemon restart
  * let backend handle replication and high availability
  * configuration-less supervision

My guidelines are:
  * keep every sub-processes autonomous (and simple)

> Home-brewed tool for now.

## Interfaces

### Livestatus

Livestatus sub-process listen to livestatus queries (port 6557 by default), then parse it over one or mutliple backends, then return results.

Database schema is quite simplified then livestatus API is quite truncated. 

>Support:
>  * hosts/services/log tables
>  * acknowledge/downtime

### Input (Custom socket line protocol)

### Nagios_Input (Nagios formatted checks results from a file)

> Not implemented yet

Also compliant with check-mk output format (same as nagios).

### Poller - needed ?

> Not implemented yet

For now, active poller may be delegated to shinken/nagios

## Inspirations

  * [Diamond](https://github.com/python-diamond/Diamond)
  * [Graphite - Carbon](https://github.com/graphite-project/carbon)