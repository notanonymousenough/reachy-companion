"""Explicit default-off owner profile; no token or device initialization."""
from pathlib import Path
from .contracts import decode


def load(path):
    value=decode(Path(path).read_bytes())
    keys={'version','enabled','listen','port','socket_path','policy_path','duration_s','camera_policy_path','stop_bound_s','guard_directory'}
    if (not isinstance(value,dict) or set(value)!=keys or type(value['version']) is not int or value['version']!=1
            or type(value['enabled']) is not bool or value['listen'] not in ('127.0.0.1','0.0.0.0')
            or type(value['port']) is not int or not 1024<=value['port']<=65535
            or type(value['duration_s']) not in (int,float) or not 0<=value['duration_s']<=300
            or value['stop_bound_s']!=.5):raise ValueError('Native owner profile')
    for key in ('socket_path','policy_path','camera_policy_path','guard_directory'):
        if not isinstance(value[key],str) or not Path(value[key]).is_absolute():raise ValueError('Native owner absolute paths required')
    if not 1<=len(value['socket_path'].encode())<=95:raise ValueError('Unix socket path bound')
    return value
