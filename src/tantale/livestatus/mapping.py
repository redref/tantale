# Fields known by tantale
KNOWN_FIELDS = (
    'type',
    'timestamp', 'hostname', 'check', 'status', 'output',
)

# Static mapping (without object names)
# coding=utf-8

FIELDS_MAPPING = {
    "state": "status",
    "name": "hostname",
    "host_name": "hostname",
    "service_description": "output",
    # No address here, only hostnames
    "address": "hostname",
    "last_state_change": "timestamp",
    "plugin_output": "output",
    "description": "check",
    "acknowledged": "ack",
    "scheduled_downtime_depth": "downtime",
    "last_check": "last_check",
    "time": "timestamp",
}

# Default values / Unwired logics
FIELDS_DUMMY = {
    "current_attempt": 1,
    "max_check_attempts": 1,
    "staleness": 0,
    "has_been_checked": 1,
    "scheduled_downtime_depth": 0,
    "check_command": 'elk',
    "notifications_enabled": 1,
    "accept_passive_checks": 1,
    "downtimes": [],
    "in_notification_period": 1,
    "active_checks_enabled": 0,
    "pnpgraph_present": 0,
    "host_action_url_expanded": None,
    "retry_interval": 60,
    "check_interval": 60,
    "last_time_ok": 0,
    "next_check": 0,
    "next_notification": 0,
    "latency": 0,
    "execution_time": 0,
    "custom_variables": {},
    "class": 1,
    "state_type": '',
    "downtime_start_time": 0,
    "downtime_end_time": 0,
    "downtime_entry_time": 0,
    "downtime_duration": 0,
}

# Data in status_table / Livestatus visible configuration
STATUS_TABLE = {
    "livestatus_version": "tantale",
    "program_version": "1.0",
    "program_start": 0,
    "num_hosts": "",
    "num_services": "",
    "enable_notifications": 0,
    "execute_service_checks": 1,
    "execute_host_checks": 1,
    "enable_flap_detection": 0,
    "enable_event_handlers": 0,
    "process_performance_data": 0,
}
