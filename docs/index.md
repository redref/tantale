[![Build Status](https://travis-ci.org/redref/tantale.svg?branch=master)](https://travis-ci.org/redref/tantale) [![Coverage Status](https://coveralls.io/repos/github/redref/tantale/badge.svg?branch=master)](https://coveralls.io/github/redref/tantale?branch=master)

# Tantale

Tantale intend to be a monitoring tool which interact with third party monitoring GUI's and tools.

Tantale store all checks/statuses (hosts/services/...) into database backend (only elasticsearch for now) in order to by fully interoperable.

Objective is to provide a Livestatus API keeping interoperability in mind.

Assumptions:
  * all configuration data is already present on hosts (with configuration management tools like puppet/chef/...)

> Tantale does not carry any configuration regarding data (groups, contacts, ...). This part must be done directly by hosts.

  * livestatus "classic" schema is quite complicated and/or redundant with backend/metrics analysis capacities.

> Tantale intend to be compatible with Livestatus, but some functionnalities may have a different behavior.

  * only passive checks

> Tantale does not get any "poller" part

Some cons:
  * monitoring results and events over time (with backend tools, NDLR grafana/kibana)
  * no need for nagios/shinken daemon restart
  * backend natively handle replication and high availability
  * configuration-less

My guidelines are:
  * keep every sub-processes autonomous (and simple)

> Home-brewed tool for now.

## Interfaces / Processes

### Livestatus

Livestatus sub-process listen to livestatus queries (port 6557 by default), then parse it over one or mutliple backends, then return results.

Database schema is quite simplified then livestatus API is quite truncated. 

>Support:
>  * hosts
>  * services
>  * log
>  * acknowledge
>  * downtime (bool flag instead of timed downtime)

> Tested livestatus client (GUI's):
>  * check-mk-multisite

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