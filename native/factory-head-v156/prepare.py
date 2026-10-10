#!/usr/bin/env python3
"""Produce a disposable source build; never install, open UART or modify inputs."""
import argparse
import hashlib
from pathlib import Path
import shutil

PINS={'control_loop.rs':'62817fbc0fd13018ba4bfc5628e1a379a822888fcbdd0792dcbe3ff2bf414df4',
      'bindings.rs':'204106cf20178b518d1bffffe76fea34b2e698a5a8fc8ac767f713e2d611e94c',
      'controller.rs':'bb618f2743e638944c65ef6839c5484319f1be2c6b74fc4d342c783a722a8843'}

def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Pinned source anchor changed: '+old[:60])
    return text.replace(old,new,1)

def prepare(source,output):
    if output.exists():raise ValueError('New disposable output directory required')
    texts={name:(source/'src'/name).read_text() for name in PINS}
    for name,expected in PINS.items():
        if hashlib.sha256(texts[name].encode()).hexdigest()!=expected:raise ValueError('Source hash mismatch: '+name)
    text=texts['control_loop.rs']
    text='mod finite_owner;\nuse finite_owner::FiniteOwner;\n'+text
    text=once(text,'    motor_name_id: HashMap<String, u8>,\n}', '    motor_name_id: HashMap<String, u8>,\n    finite_owner: Arc<FiniteOwner>,\n    finite_execution: Arc<Mutex<()>>,\n}')
    text=once(text,'    let stop_signal = Arc::new(Mutex::new(false));','    let finite_owner = Arc::new(FiniteOwner::new());\n        let finite_owner_clone=finite_owner.clone();\n        let finite_execution=Arc::new(Mutex::new(()));\n        let finite_execution_clone=finite_execution.clone();\n        let stop_signal = Arc::new(Mutex::new(false));')
    text=once(text,'                read_allowed_retries,\n            );','                read_allowed_retries,\n                finite_owner_clone,\n                finite_execution_clone,\n            );')
    text=once(text,'            motor_name_id,\n        })','            motor_name_id,\n            finite_owner,\n            finite_execution,\n        })')
    methods='''    // Single-use latch outside the command queue. Arm rejects an actual occupied
    // native slot and serialized admission discards all pre-arm queued mutators.
    pub fn finite_arm(&self, owner: &str, duration_ms:u64, policy_ms:u64) -> Result<(), String> {
        let _slot=self.finite_execution.try_lock().map_err(|_| "native execution busy")?;
        self.finite_owner.arm(owner,duration_ms,policy_ms).map_err(String::from)
    }
    pub fn finite_refresh(&self, owner:&str, remaining_ms:u64) -> Result<(), String> {
        self.finite_owner.refresh(owner,remaining_ms).map_err(String::from)
    }
    pub fn finite_revoke(&self, owner:&str) -> Result<(), String> {
        self.finite_owner.revoke(owner).map_err(String::from)
    }
    pub fn finite_withdrawn(&self) -> bool { self.finite_owner.withdrawn() }

'''
    text=once(text,'    pub fn push_command(\n',methods+'    pub fn push_command(\n')
    text=once(text,'        self.tx.blocking_send(command)','''        if self.finite_owner.sealed() {
            // No finite motion admission yet: all mutators, raw writes, reboot,
            // mode and torque commands are denied even before queue admission.
            if !matches!(&command,MotorCommand::ReadRawBytes { id:10..=18, addr:0|64|132, length:1|2|4, .. }) {
                return Err(mpsc::error::SendError(command));
            }
        }
        self.tx.blocking_send(command)''')
    text=once(text,'    read_allowed_retries: u64,\n) {','    read_allowed_retries: u64,\n    finite_owner: Arc<FiniteOwner>,\n    finite_execution: Arc<Mutex<()>>,\n) {')
    text=once(text,'        loop {\n            tokio::select!', '''        loop {
            // This runs on the EXISTING serial owner, independently of Python.
            // Each serial operation still needs measured bounded-I/O evidence.
            if finite_owner.withdrawn() {
                while rx.try_recv().is_ok() {} // DROP pending work; never drain into hardware
                let _slot=finite_execution.lock().unwrap();
                // Retry at the loop boundary, not inside an ordinary command.
                // ACK is not all-nine measured torque-off/held-pose proof.
                let _=c.disable_torque();
                drop(_slot);
                std::thread::sleep(Duration::from_millis(5));
                if *stop_signal.lock().unwrap() { break; }
                continue;
            }
            tokio::select!''')
    old='''                        if handle_commands(&mut c, last_torque.clone(), last_control_mode.clone(), command, read_allowed_retries).is_ok() {'''
    new='''                        let _slot=finite_execution.lock().unwrap();
                        let finite=finite_owner.sealed();
                        if finite_owner.withdrawn() || (finite && !matches!(&command,MotorCommand::ReadRawBytes { id:10..=18, addr:0|64|132, length:1|2|4, .. })) { continue; }
                        let retries=if finite { 1 } else { read_allowed_retries };
                        if handle_commands(&mut c, last_torque.clone(), last_control_mode.clone(), command, retries).is_ok() {'''
    text=once(text,old,new)
    text=once(text,'                    match read_pos(&mut c, read_allowed_retries) {','''                    let _slot=finite_execution.lock().unwrap();
                    if finite_owner.withdrawn() { continue; }
                    let retries=if finite_owner.sealed() { 1 } else { read_allowed_retries };
                    match read_pos(&mut c, retries) {''')
    text=once(text,'                // Drain the command channel before exiting','''                if finite_owner.sealed() {
                    while rx.try_recv().is_ok() {}
                    let _=c.disable_torque();
                    break;
                }
                // Drain the command channel before exiting''')
    binding=texts['bindings.rs']
    old='''    fn async_read_raw_bytes(&self, id: u8, addr: u8, length: u8) -> PyResult<Vec<u8>> {
        self.inner
            .async_read_raw_bytes(id, addr, length)'''
    new='''    fn async_read_raw_bytes(&self, py: Python<'_>, id: u8, addr: u8, length: u8) -> PyResult<Vec<u8>> {
        py.detach(|| self.inner.async_read_raw_bytes(id, addr, length))'''
    binding=once(binding,old,new)
    api='''    fn finite_arm(&self, owner:String, duration_ms:u64, policy_ms:u64) -> PyResult<()> {
        self.inner.finite_arm(&owner,duration_ms,policy_ms).map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }
    fn finite_refresh(&self, owner:String, remaining_ms:u64) -> PyResult<()> {
        self.inner.finite_refresh(&owner,remaining_ms).map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }
    fn finite_revoke(&self, owner:String) -> PyResult<()> {
        self.inner.finite_revoke(&owner).map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }
    fn finite_withdrawn(&self) -> bool { self.inner.finite_withdrawn() }
'''
    binding=once(binding,'    /// Perform an asynchronous raw read of motor bytes.',api+'    /// Perform an asynchronous raw read of motor bytes.')
    # Keep the original source tree and lockfile intact in a new build directory.
    shutil.copytree(source,output,ignore=shutil.ignore_patterns('.git','target','.venv'))
    (output/'src'/'control_loop.rs').write_text(text)
    (output/'src'/'bindings.rs').write_text(binding)
    # A child module of control_loop is resolved in src/control_loop/.
    (output/'src'/'control_loop').mkdir(exist_ok=True)
    shutil.copyfile(Path(__file__).with_name('finite_owner.rs'),output/'src'/'control_loop'/'finite_owner.rs')
    cargo=(output/'Cargo.toml').read_text()
    (output/'Cargo.toml').write_text(once(cargo,'version = "1.5.6"','version = "1.5.6-finite-head.1"'))
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();print(prepare(args.source,args.output))
