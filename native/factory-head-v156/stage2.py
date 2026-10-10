"""Source-pinned owned operations extension; used only by prepare.py."""
from prepare import once

def extend(text,binding):
    text='mod finite_engine;\nuse finite_engine::{Engine,SerialOps};\n'+text
    text=once(text,'    finite_execution: Arc<Mutex<()>>,\n}', '''    finite_execution: Arc<Mutex<()>>,
    finite_engine: Arc<Mutex<Engine>>,
    finite_actions: Arc<Mutex<HashMap<String,Option<Result<(),String>>>>>,
}''')
    text=once(text,'    EnableTorque(),','''    FiniteEnable { owner:String, action:String },
    FiniteGoals { owner:String, action:String, positions:[f64;9] },
    EnableTorque(),''')
    text=once(text,'        let mut interval = time::interval(read_position_loop_period);','''        let mut interval = time::interval(read_position_loop_period);
        let mut finite_watchdog=time::interval(Duration::from_millis(5));''')
    text=once(text,'            tokio::select! {','''            tokio::select! {
                _ = finite_watchdog.tick() => {} // absolute/policy latch checked at loop top''')
    text=once(text,'        let finite_owner_clone=finite_owner.clone();','''        let finite_owner_clone=finite_owner.clone();
        let finite_engine=Arc::new(Mutex::new(Engine::default()));
        let finite_engine_clone=finite_engine.clone();
        let finite_actions=Arc::new(Mutex::new(HashMap::new()));
        let finite_actions_clone=finite_actions.clone();''')
    text=once(text,'                finite_execution_clone,\n','                finite_execution_clone,\n                finite_engine_clone,\n                finite_actions_clone,\n')
    text=once(text,'            finite_execution,\n        })','            finite_execution,\n            finite_engine,\n            finite_actions,\n        })')
    methods='''    fn finite_enqueue(&self,owner:&str,action:&str,command:MotorCommand)->Result<(),String> {
        if action.is_empty() || action.len()>128 || !self.finite_owner.admit(owner) { return Err("withdrawn/invalid native action".into()) }
        let mut actions=self.finite_actions.lock().map_err(|_| "actions poisoned")?;
        if actions.len()>=256 || actions.contains_key(action) { return Err("native action reused/full".into()) }
        actions.insert(action.into(),None);
        // No blocking_send: actual slot is occupied until the native result is recorded.
        if self.tx.try_send(command).is_err() {
            actions.insert(action.into(),Some(Err("native queue full/closed".into())));
            return Err("native queue full/closed".into());
        }
        Ok(())
    }
    pub fn finite_enable(&self,owner:String,action:String,generation:u64)->Result<(),String> {
        if generation!=0 { return Err("native generation mismatch".into()) }
        self.finite_enqueue(&owner,&action,MotorCommand::FiniteEnable {owner:owner.clone(),action:action.clone()})
    }
    pub fn finite_goals(&self,owner:String,action:String,generation:u64,positions:[f64;9])->Result<(),String> {
        if generation!=0 { return Err("native generation mismatch".into()) }
        self.finite_enqueue(&owner,&action,MotorCommand::FiniteGoals {owner:owner.clone(),action:action.clone(),positions})
    }
    pub fn finite_receipt(&self,action:&str)->String {
        let Ok(actions)=self.finite_actions.try_lock() else { return "unknown".into() };
        match actions.get(action) {
            Some(None)=>"pending".into(),Some(Some(Ok(())))=>"accepted".into(),
            Some(Some(Err(error)))=>format!("rejected:{}",error),None=>"unknown".into()
        }
    }
    pub fn finite_status(&self)->(bool,bool,bool,f64,Vec<f64>,Vec<bool>,u64) {
        let withdrawn=self.finite_owner.withdrawn();
        let busy=self.finite_execution.try_lock().is_err()
            || self.finite_actions.try_lock().map(|m| m.values().any(|r| r.is_none())).unwrap_or(true);
        let Ok(engine)=self.finite_engine.try_lock() else {return (withdrawn,true,false,f64::INFINITY,vec![],vec![],0)};
        match &engine.latest {
            Some(sample)=>(withdrawn,busy,!busy && withdrawn && engine.stop_known(),sample.started.elapsed().as_secs_f64(),sample.positions.to_vec(),sample.torque.to_vec(),sample.sequence),
            None=>(withdrawn,busy,false,f64::INFINITY,vec![],vec![],0)
        }
    }

'''
    text=once(text,'    pub fn push_command(\n',methods+'    pub fn push_command(\n')
    text=once(text,'    finite_execution: Arc<Mutex<()>>,\n) {','''    finite_execution: Arc<Mutex<()>>,
    finite_engine:Arc<Mutex<Engine>>,
    finite_actions:Arc<Mutex<HashMap<String,Option<Result<(),String>>>>>,
) {''')
    text=once(text,'                while rx.try_recv().is_ok() {} // DROP pending work; never drain into hardware','')
    text=once(text,'                let _=c.disable_torque();\n                drop(_slot);','''                finite_engine.lock().unwrap().stop_before_bounded_purge(&mut c,finite_owner.withdrawn_at(),|| {
                    match rx.try_recv() { Ok(command)=>{finite_discard(command,&finite_actions);true},Err(_)=>false }
                });
                drop(_slot);''')
    text=once(text,'                        let finite=finite_owner.sealed();','''                        let finite=finite_owner.sealed();
                        match command {
                            MotorCommand::FiniteEnable {ref owner,ref action} | MotorCommand::FiniteGoals {ref owner,ref action,..} => {
                                let owner=owner.clone();let action=action.clone();
                                let mut engine=finite_engine.lock().unwrap();
                                let result=match command {
                                    MotorCommand::FiniteEnable {..}=>engine.pin_enable(&mut c,&finite_owner,&owner),
                                    MotorCommand::FiniteGoals {positions,..}=>engine.goals(&mut c,&finite_owner,&owner,positions),
                                    _=>unreachable!()
                                };
                                if result.is_err() {let _=finite_owner.revoke(&owner);}
                                finite_actions.lock().unwrap().insert(action,Some(result));
                                continue;
                            }
                            _=>{}
                        }''')
    text=once(text,'                    while rx.try_recv().is_ok() {}\n                    let _=c.disable_torque();','''                    finite_engine.lock().unwrap().stop_before_bounded_purge(&mut c,finite_owner.withdrawn_at(),|| {
                        match rx.try_recv() { Ok(command)=>{finite_discard(command,&finite_actions);true},Err(_)=>false }
                    });''')
    text=once(text,'            // No finite motion admission yet: all mutators, raw writes, reboot,','''            if self.finite_owner.withdrawn() { return Err(mpsc::error::SendError(command)); }
            // Ordinary mutators, raw writes, reboot,''')
    text=once(text,'        self.tx.blocking_send(command)','''        if self.finite_owner.sealed() {
            return self.tx.try_send(command).map_err(|e| mpsc::error::SendError(e.into_inner()));
        }
        self.tx.blocking_send(command)''')
    # Prevent even crate-level accidental invocation of scoped commands through
    # the legacy dispatcher: there is exactly one reviewed owned dispatch site.
    text=once(text,'    match command {\n        SetAllGoalPositions','    match command {\n        FiniteEnable {..} | FiniteGoals {..} => Err("owned dispatcher required".into()),\n        SetAllGoalPositions')
    text+='''
fn finite_discard(command:MotorCommand,actions:&Arc<Mutex<HashMap<String,Option<Result<(),String>>>>>) {
    match command {
        MotorCommand::FiniteEnable {action,..}|MotorCommand::FiniteGoals {action,..}=>{
            actions.lock().unwrap().insert(action,Some(Err("withdrawn before execution".into())));
        }
        _=>{} // dropping ReadRawBytes also disconnects its awaiting sender
    }
}
impl SerialOps for ReachyMiniMotorController {
    fn positions(&mut self)->Result<[f64;9],String>{ self.read_all_positions().map_err(|e| e.to_string()) }
    fn torque(&mut self,id:u8)->Result<bool,String>{
        match self.read_raw_bytes(id,64,1).map_err(|e| e.to_string())?.as_slice() {
            [0]=>Ok(false),[1]=>Ok(true),_=>Err("invalid all-nine torque response".into())
        }
    }
    fn position_mode(&mut self,id:u8)->Result<bool,String>{
        Ok(self.read_raw_bytes(id,11,1).map_err(|e| e.to_string())?.as_slice()==[3])
    }
    fn goals(&mut self,value:[f64;9])->Result<(),String>{self.set_all_goal_positions(value).map_err(|e| e.to_string())}
    fn enable(&mut self)->Result<(),String>{self.enable_torque().map_err(|e| e.to_string())}
    fn disable(&mut self)->Result<(),String>{self.disable_torque().map_err(|e| e.to_string())}
}
'''
    api='''    fn finite_enable(&self,owner:String,action:String,generation:u64)->PyResult<()> {
        self.inner.finite_enable(owner,action,generation).map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }
    fn finite_goals(&self,owner:String,action:String,generation:u64,positions:[f64;9])->PyResult<()> {
        self.inner.finite_goals(owner,action,generation,positions).map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }
    fn finite_receipt(&self,action:String)->String {self.inner.finite_receipt(&action)}
    fn finite_status(&self)->(bool,bool,bool,f64,Vec<f64>,Vec<bool>,u64) {self.inner.finite_status()}
'''
    binding=once(binding,'    fn finite_withdrawn(&self) -> bool',api+'    fn finite_withdrawn(&self) -> bool')
    return text,binding
