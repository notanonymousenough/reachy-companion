"""Pin and fence the vendor's pre-controller reflash path, process locally."""
import ast
import hashlib
import inspect
from pathlib import Path,PurePosixPath
import sys
import threading
from types import CodeType,FunctionType

SETUP_SEGMENT_SHA256='206f03c2cad77a82faa2be11d3a5b8db0a3fca1d7418bc1ef7404c609bdb370e'
PARAMETERS=('self','wireless_version','sim','mockup_sim','serialport','scene','check_collision',
    'kinematics_engine','headless','use_audio','hardware_config_filepath','reflash_motors_on_start')


def review_startup(daemon_class,robot_class,serialport,source_sha256):
    if (type(serialport) is not str or not serialport.startswith('/dev/') or len(serialport)>256
            or '\x00' in serialport or '\\' in serialport or '..' in serialport.split('/')
            or str(PurePosixPath(serialport))!=serialport):raise ValueError('Explicit frozen Linux UART path required; no auto discovery')
    source=inspect.getsourcefile(daemon_class)
    if source is None:raise ValueError('Pinned daemon source required')
    raw=Path(source).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=source_sha256:raise ValueError('Daemon startup source changed')
    tree=ast.parse(raw);classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==daemon_class.__name__]
    methods=[n for c in classes for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='_setup_backend']
    if len(classes)!=1 or len(methods)!=1:raise ValueError('Exact pinned sync startup method required')
    segment=ast.get_source_segment(raw.decode(),methods[0])
    if hashlib.sha256(segment.encode()).hexdigest()!=SETUP_SEGMENT_SHA256:raise ValueError('Unknown vendor startup/reflash shape')
    original=vars(daemon_class).get('_setup_backend');module=inspect.getmodule(daemon_class)
    if (type(original) is not FunctionType or module is None or original.__globals__ is not vars(module)
            or inspect.getsourcefile(original)!=source or getattr(module,'RobotBackend',None) is not robot_class):
        raise ValueError('Actual daemon function/global/backend binding required')
    compiled=compile(raw,source,'exec',dont_inherit=True,optimize=sys.flags.optimize)
    class_code=next(c for c in compiled.co_consts if isinstance(c,CodeType) and c.co_name==daemon_class.__name__)
    method_code=next(c for c in class_code.co_consts if isinstance(c,CodeType) and c.co_name=='_setup_backend')
    if original.__code__!=method_code:raise ValueError('Runtime daemon method differs from pinned source')
    signature=inspect.signature(original,follow_wrapped=False)
    defaults=original.__defaults__
    if (tuple(signature.parameters)!=PARAMETERS or type(defaults) is not tuple or len(defaults)!=2
            or defaults[0] is not None or defaults[1] is not True or original.__kwdefaults__ is not None
            or any(p.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD for p in signature.parameters.values())):
        raise ValueError('Exact vendor startup signature/defaults required')
    raw_reflash=vars(module).get('reflash_motors_if_needed')
    tools=sys.modules.get('reachy_mini.tools.reflash_motors')
    if (type(raw_reflash) is not FunctionType or tools is None or raw_reflash.__globals__ is not vars(tools)
            or getattr(tools,'reflash_motors_if_needed',None) is not raw_reflash):
        raise ValueError('Exact raw reflash global binding required')
    return dict(daemon_class=daemon_class,module=module,tools=tools,original=original,
        signature=signature,serialport=serialport,robot_class=robot_class)


def install_startup_fence(review):
    daemon=review['daemon_class'];module=review['module'];tools=review['tools'];original=review['original']
    start_lock=threading.Lock();entered=[False]
    def forbid_reflash(*args,**kwargs):raise ValueError('Motor reflash is forbidden in readonly factory process')
    def setup_readonly(self,*args,**kwargs):
        if (type(self) is not daemon or daemon._setup_backend is not setup_readonly
                or module.reflash_motors_if_needed is not forbid_reflash or tools.reflash_motors_if_needed is not forbid_reflash
                or module.RobotBackend is not review['robot_class']):raise ValueError('Startup fence binding changed')
        bound=review['signature'].bind(self,*args,**kwargs);bound.apply_defaults();values=bound.arguments
        if (type(values['serialport']) is not str or values['serialport']!=review['serialport']
                or any(values[key] is not False for key in ('wireless_version','sim','mockup_sim','check_collision','use_audio'))
                or values['hardware_config_filepath'] is not None or values['kinematics_engine']!='AnalyticalKinematics'):
            raise ValueError('Readonly explicit-port backend profile required')
        values['reflash_motors_on_start']=False # own both positional and keyword/default paths
        with start_lock:
            if entered[0]:raise ValueError('Readonly factory startup is single-use, including unknown failures')
            entered[0]=True
        return original(*bound.args,**bound.kwargs)
    module.reflash_motors_if_needed=tools.reflash_motors_if_needed=forbid_reflash
    daemon._setup_backend=setup_readonly
    return dict(startup_daemon_class=daemon,startup_module=module,startup_tools_module=tools,
        readonly_setup=setup_readonly,reflash_trap=forbid_reflash,explicit_serialport=review['serialport'])


def startup_fence_intact(preparation):
    return (preparation['startup_daemon_class']._setup_backend is preparation['readonly_setup']
        and preparation['startup_module'].reflash_motors_if_needed is preparation['reflash_trap']
        and preparation['startup_tools_module'].reflash_motors_if_needed is preparation['reflash_trap']
        and preparation['startup_module'].RobotBackend is preparation['backend_class'])
