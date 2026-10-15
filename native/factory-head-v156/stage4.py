"""Read-only finite startup, applied after the pinned .3 generator stages."""
from prepare import once


def extend(text,binding):
    text='pub(crate) mod finite_startup;\n'+text
    text=once(text,'    finite_actions: Arc<Mutex<HashMap<String,Option<Result<(),String>>>>>,\n}',
        '    finite_actions: Arc<Mutex<HashMap<String,Option<Result<(),String>>>>>,\n    readonly_startup: bool,\n}')
    text=once(text,'        let finite_owner = Arc::new(FiniteOwner::new());',
        '        let readonly_startup=finite_startup::PROCESS.claim().map_err(|_|MotorError::CommunicationError())?;\n        let finite_owner = Arc::new(FiniteOwner::new());')
    a=text.index('        match c.check_missing_ids() {');b=text.index('        let last_position = Arc::new',a)
    legacy=text[a:b]
    text=text[:a]+'''        let (motor_name_id,last_position,last_torque,last_control_mode)=if readonly_startup {
            let initial=finite_startup::check(&mut c).map_err(|_|MotorError::CommunicationError())?;
            (c.get_motor_name_id(),FullBodyPosition::new(initial.positions[0],initial.positions[1..7].to_vec(),initial.positions[7..9].to_vec()),false,initial.mode)
        } else {
'''+legacy+'''            (motor_name_id,last_position,last_torque,last_control_mode)
        };

'''+text[b:]
    text=once(text,'                finite_actions_clone,\n','                finite_actions_clone,\n                readonly_startup,\n')
    text=once(text,'            finite_actions,\n        })','            finite_actions,\n            readonly_startup,\n        })')
    text=once(text,'    finite_actions:Arc<Mutex<HashMap<String,Option<Result<(),String>>>>>,\n) {',
        '    finite_actions:Arc<Mutex<HashMap<String,Option<Result<(),String>>>>>,\n    readonly_startup:bool,\n) {')
    # The native read-only guard precedes Python authority and every queue entry.
    text=text.replace('self.finite_owner.sealed()', 'self.readonly_startup || self.finite_owner.sealed()')
    text=once(text,'let finite=finite_owner.sealed();','let finite=readonly_startup || finite_owner.sealed();')
    text=once(text,'let retries=if finite_owner.sealed() { 1 }','let retries=if readonly_startup || finite_owner.sealed() { 1 }')
    coarse='MotorCommand::ReadRawBytes { id:10..=18, addr:0|64|132, length:1|2|4, .. }'
    # One predicate is shared by enqueue and actual execution; scoped finite
    # operations still use their separate owner-checked native dispatcher.
    old='matches!(&command,'+coarse+')'
    if text.count(old)!=2:raise ValueError('Pinned read-only dispatcher anchors changed')
    text=text.replace(old,'finite_startup::ordinary_allowed(&command)')
    text=once(text,'                // Drain the command channel before exiting', '''                if readonly_startup {
                    // Unarmed read-only startup has never enabled/goaled motors.
                    // Drop pending reads; never execute queued work on close.
                    for _ in 0..100 {if rx.try_recv().is_err(){break}}
                    break;
                }
                // Drain the command channel before exiting''')
    text=once(text,'    pub fn close(&self) {','    pub fn readonly_startup(&self)->bool {self.readonly_startup}\n\n    pub fn close(&self) {')
    text+='''
impl finite_startup::ReadOnlyIo for ReachyMiniMotorController {
    fn read(&mut self,id:u8,address:u8,length:u8)->Result<Vec<u8>,String> {
        self.read_raw_bytes(id,address,length).map_err(|e|e.to_string())
    }
}
'''
    binding=once(binding,'        let inner = Controller::new(&serialport)',
        '        crate::control_loop::finite_startup::PROCESS.claim_legacy().map_err(pyo3::exceptions::PyRuntimeError::new_err)?;\n        let inner = Controller::new(&serialport)')
    # The synchronous native constructor remains untouched in ordinary mode.
    anchor='''    fn new(
        serialport: String,
        read_position_loop_period: Duration,'''
    binding=once(binding,anchor,'''    fn new(
        py:Python<'_>,
        serialport: String,
        read_position_loop_period: Duration,''')
    binding=once(binding,'        let control_loop = ReachyMiniControlLoop::new(', '        let build=||ReachyMiniControlLoop::new(')
    binding=once(binding,'''        )
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(ReachyMiniPyControlLoop {''', '''        );
        let control_loop=if crate::control_loop::finite_startup::PROCESS.requested(){py.detach(build)}else{build()}
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(ReachyMiniPyControlLoop {''')
    binding=once(binding,'''    fn close(&self) -> PyResult<()> {
        self.inner.close();''', '''    fn close(&self,py:Python<'_>) -> PyResult<()> {
        if self.inner.readonly_startup(){py.detach(||self.inner.close())}else{self.inner.close()};''')
    api='''    #[staticmethod]
    fn finite_prepare_readonly_startup()->PyResult<()> {
        crate::control_loop::finite_startup::PROCESS.prepare().map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }
    #[staticmethod]
    fn finite_startup_status()->(bool,bool,u64,Vec<u8>,Vec<bool>,f64) {
        let requested=crate::control_loop::finite_startup::PROCESS.requested();
        match crate::control_loop::finite_startup::RECEIPT.lock() {
            Ok(value)=>match value.as_ref(){Some(r)=>(requested,r.complete,r.reads,r.health.clone(),r.torque.clone(),r.elapsed_ms),None=>(requested,false,0,vec![],vec![],0.)},
            Err(_)=>(requested,false,0,vec![],vec![],f64::INFINITY)
        }
    }
'''
    binding=once(binding,'    #[staticmethod]\n    fn finite_clock_ns()',api+'    #[staticmethod]\n    fn finite_clock_ns()')
    return text,binding
