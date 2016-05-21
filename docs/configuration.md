# Configuration guide

Configuration file located in /etc/tantale/tantale.conf. You may look at the example.

Use python ConfigObj syntax.

## Daemon options

```
[server]
user =
group =
pid_file = /var/run/tantale.pid
```

Specify user, group to use when forking daemon and pidfile location.

## Livestatus options

```
[modules]
[[Livestatus]]
enabled = True
port = 6557
```

## Input options

```
[[Input]]
enabled = True
port = 2003

# Max time (in seconds) check may wait others (in backend POV)
ttl = 5

# Freshness timeout (warning if check not fresh)
#  status => 1, ouput prefixed with 'OUTDATED '
#freshness_timeout = 120

# Maximum number of checks waiting to be processed.
# When queue is full, new are dropped.
queue_size = 16384
```

## Client options

```
[[Client]]
# enabled = False

# Global refresh interval
#   Force push every X seconds
# interval = 30

# Tantale Input server
server_host = 127.0.0.1
server_port = 2003

# Contacts_groups for the host
contacts = user_1, user_2

# Diamond source configuration
#   Input FIFO file path - must match diamond Handler config
# diamond_fifo = /dev/shm/diamond_to_fifo

# External source configuration
#   Pre-forked workers number
# external_workers = 3

# Checks definition

# All checks config keys
#   hostname = <local fqdn>
#     usefull to submit checks for other hosts

# Host check - wired to host livestatus object
[[[Host]]]
# "ok" report sucessfull at any time
type = ok

[[[Host-fqdn.domain]]]
# "ok" report sucessfull at any time
name = Host
type = ok
hostname = fqdn.domain

# Process ('ps') source example
[[[ps_example]]]
type = ps

# Filter processes by regexp (required)
regexp = 'in[ia]t'

# Filter processes by user (no filter if not defined)
user = root

# Check number of process (low crit, low warn, up warn, up crit)
thresholds = 1, 1, "", ""

# External commands source example
[[[external_example]]]
type = external
command = /bin/bash -c 'echo fail; exit 1'

# Launch this check every X seconds
# interval = 60


# Diamond source example
[[[fs_root]]]
type = diamond
hostname = fqdn.domain

# Prefix added to expression metrics
#   Default : ""
prefix = servers.domain.my_fqdn

# Mathematic expression
expression = "( {diskspace.root.byte_free} / {diskspace.root.byte_avail} ) * 100"

# Check expression value range (low crit, low warn, up warn, up crit)
thresholds = 10, 20, "", ""
```

## Backends options (only Elasticsearch right now)

```
[backends]

[[ElasticsearchBackend]]
# python-elasticsearch options
hosts = http://127.0.0.1:9200
use_ssl = False
verify_certs = False
ca_certs = ''
sniffer_timeout = 30
sniff_on_start = True
sniff_on_connection_fail = True

# index options
status_index = test_status
log_index = test_status_logs
log_index_rotation = 'daily'
request_timeout = 30

# Backend specific options
# Maximum size for batch update
batch = 1000
# maximum checks keeped in memory (FIFO) in case backend failing (trim)
backlog_size = 2000
```

## Logging options

```
# Will be merged with tantale minimal configuration.
# You may need to use or override minimal configuration defined objects 
# Here a list of usefull ones

# [[handlers]]
# [[[stdout]]]
# class = logging.StreamHandler
# level = NOTSET
# formatter = default
# stream = ext://sys.stdout
# [[[null]]]
# class = logging.NullHandler
# level = NOTSET
# [[formatters]]
# [[[default]]]
# format = '[%(asctime)s] %(levelname)8s [%(processName)s] %(message)s'
# datefmt = '%Y-%m-%d %H:%M:%S'

[logging]

[[loggers]]

[[[tantale]]]
level = INFO
handlers = rotated_file,

# Example overriding livestatus specific logger
#[[[tantale.livestatus]]]
#level = DEBUG

[[handlers]]

[[[rotated_file]]]
class = logging.handlers.TimedRotatingFileHandler
level = NOTSET
formatter = default
# Rotate at midnight, each day and keep 7 days
filename = /var/log/tantale/tantale.log
when = midnight
interval = 1
backupCount = 7
```