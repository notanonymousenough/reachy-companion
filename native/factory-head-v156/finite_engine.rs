//! Finite operations on the existing serial owner. Hardware admission remains
//! dependent on bounded-I/O evidence, factory producer fences and measured FK.
use super::finite_owner::FiniteOwner;
use std::time::{Duration,Instant};

pub trait SerialOps {
    fn positions(&mut self)->Result<[f64;9],String>;
    fn torque(&mut self,id:u8)->Result<bool,String>;
    fn position_mode(&mut self,id:u8)->Result<bool,String>;
    fn goals(&mut self,value:[f64;9])->Result<(),String>;
    fn enable(&mut self)->Result<(),String>;
    fn disable(&mut self)->Result<(),String>;
}
#[derive(Clone)]
pub struct Observation { pub started:Instant, pub finished:Instant, pub positions:[f64;9], pub torque:[bool;9],pub sequence:u64 }
#[derive(Default)]
pub struct Engine {
    pub baseline:Option<[f64;9]>, pub latest:Option<Observation>,
    stop_started:Option<Instant>, stop_written:bool, held:Vec<Observation>,sequence:u64,
}
impl Engine {
    pub fn stop_before_bounded_purge<T:SerialOps,F:FnMut()->bool>(&mut self,io:&mut T,withdrawn_at:Option<Instant>,mut purge:F) {
        self.stop_tick(io,withdrawn_at); // priority stop before consulting any producer queue
        for _ in 0..100 { if !purge() { break } }
    }
    fn active(gate:&FiniteOwner,owner:&str)->Result<(),String> {
        if gate.admit(owner) { Ok(()) } else { Err("finite owner withdrawn/mismatched".into()) }
    }
    pub fn sample<T:SerialOps>(&mut self,io:&mut T,gate:&FiniteOwner,owner:&str)->Result<Observation,String> {
        self.latest=None;Self::active(gate,owner)?;
        let started=Instant::now();let positions=io.positions()?;Self::active(gate,owner)?;
        if positions.iter().any(|n| !n.is_finite()) { return Err("invalid native positions".into()) }
        let mut torque=[false;9];
        for (n,value) in torque.iter_mut().enumerate() {
            Self::active(gate,owner)?;*value=io.torque(10+n as u8)?;Self::active(gate,owner)?;
            if started.elapsed()>Duration::from_millis(100) { return Err("native group stale".into()) }
        }
        self.sequence+=1;
        let sample=Observation { started,finished:Instant::now(),positions,torque,sequence:self.sequence };
        self.latest=Some(sample.clone());Ok(sample)
    }
    pub fn pin_enable<T:SerialOps>(&mut self,io:&mut T,gate:&FiniteOwner,owner:&str)->Result<(),String> {
        if self.baseline.is_some() { return Err("finite enable already used".into()) }
        let sample=self.sample(io,gate,owner)?;
        if sample.torque.iter().any(|v| *v) { return Err("disabled baseline required".into()) }
        for id in 10..=18 {
            Self::active(gate,owner)?;
            if !io.position_mode(id)? { return Err("all-nine position mode required".into()) }
            Self::active(gate,owner)?;
            if sample.started.elapsed()>Duration::from_millis(100) { return Err("enable baseline stale".into()) }
        }
        Self::active(gate,owner)?;io.goals(sample.positions)?; // measured pin BEFORE torque
        Self::active(gate,owner)?;
        if sample.started.elapsed()>Duration::from_millis(100) { return Err("enable pin stale".into()) }
        // Set once BEFORE potential uncertain enable outcome; never retry enable.
        self.baseline=Some(sample.positions);io.enable()?;Self::active(gate,owner)
    }
    pub fn goals<T:SerialOps>(&mut self,io:&mut T,gate:&FiniteOwner,owner:&str,value:[f64;9])->Result<(),String> {
        Self::active(gate,owner)?;let base=self.baseline.ok_or("owned enable required")?;
        for n in 0..9 {
            let bound=if n==0 || n>=7 { 0.0001 } else { 0.06 };
            if !value[n].is_finite() || (value[n]-base[n]).abs()>bound { return Err("native relative joint scope exceeded".into()) }
        }
        // Native joint bounds supplement, never replace the bounded Cartesian
        // plan and fresh FK performed by the reviewed factory adapter.
        Self::active(gate,owner)?;io.goals(value)?;Self::active(gate,owner)
    }
    pub fn stop_tick<T:SerialOps>(&mut self,io:&mut T,withdrawn_at:Option<Instant>) {
        // SLA starts at native expiry/revoke, NEVER after a delayed I/O returns.
        if let Some(start)=withdrawn_at { self.stop_started.get_or_insert(start); }
        self.latest=None;
        if !self.stop_written { self.stop_written=io.disable().is_ok(); }
        if !self.stop_written { self.held.clear();return }
        let started=Instant::now();
        let Ok(positions)=io.positions() else { self.held.clear();return };
        if positions.iter().any(|v| !v.is_finite()) { self.held.clear();return }
        let mut torque=[false;9];
        for (n,value) in torque.iter_mut().enumerate() {
            let Ok(enabled)=io.torque(10+n as u8) else { self.held.clear();return };
            *value=enabled;
            if started.elapsed()>Duration::from_millis(100) { self.held.clear();return }
        }
        self.sequence+=1;
        let sample=Observation { started,finished:Instant::now(),positions,torque,sequence:self.sequence };
        if torque.iter().any(|v| *v) { self.stop_written=false;self.held.clear();self.latest=Some(sample);return }
        if let Some(last)=self.held.last() {
            let dt=started.duration_since(last.started).as_secs_f64();
            if dt<=0. || positions.iter().zip(last.positions).any(|(a,b)| (a-b).abs()/dt>0.05) { self.held.clear(); }
        }
        self.latest=Some(sample.clone());self.held.push(sample);
        if self.held.len()>32 { self.held.remove(0); }
    }
    pub fn stop_known(&self)->bool {
        let Some(start)=self.stop_started else { return false };
        let (Some(first),Some(last))=(self.held.first(),self.held.last()) else { return false };
        self.stop_written && self.held.len()>=3 && last.started.duration_since(first.started)>=Duration::from_millis(100)
            && last.started.elapsed()<=Duration::from_millis(100) && start.elapsed()<=Duration::from_millis(500)
            && last.finished.duration_since(last.started)<=Duration::from_millis(100)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    struct Fake { log:Vec<&'static str>, positions:[f64;9], torque:bool, gate:Arc<FiniteOwner>, revoke_on_pin:bool, fail_disable:bool,delay:Duration,priority:Arc<std::sync::atomic::AtomicBool> }
    impl SerialOps for Fake {
        fn positions(&mut self)->Result<[f64;9],String>{self.log.push("positions");std::thread::sleep(self.delay);Ok(self.positions)}
        fn torque(&mut self,_:u8)->Result<bool,String>{Ok(self.torque)}
        fn position_mode(&mut self,_:u8)->Result<bool,String>{Ok(true)}
        fn goals(&mut self,_:[f64;9])->Result<(),String>{self.log.push("goals");if self.revoke_on_pin {self.gate.revoke("owner").unwrap();}Ok(())}
        fn enable(&mut self)->Result<(),String>{self.log.push("enable");self.torque=true;Ok(())}
        fn disable(&mut self)->Result<(),String>{self.log.push("disable");self.priority.store(true,std::sync::atomic::Ordering::SeqCst);if self.fail_disable {return Err("serial unknown".into())}self.torque=false;Ok(())}
    }
    fn fake()->Fake { let gate=Arc::new(FiniteOwner::new());gate.arm("owner",4000,300).unwrap();Fake{log:vec![],positions:[0.;9],torque:false,gate,revoke_on_pin:false,fail_disable:false,delay:Duration::ZERO,priority:Arc::new(std::sync::atomic::AtomicBool::new(false))} }
    #[test] fn pin_precedes_enable_and_withdraw_between_them_blocks_enable() {
        let mut io=fake();let gate=io.gate.clone();let mut engine=Engine::default();engine.pin_enable(&mut io,&gate,"owner").unwrap();
        assert_eq!(io.log,vec!["positions","goals","enable"]);
        let mut io=fake();io.revoke_on_pin=true;let gate=io.gate.clone();let mut engine=Engine::default();
        assert!(engine.pin_enable(&mut io,&gate,"owner").is_err());assert!(!io.log.contains(&"enable"));
    }
    #[test] fn enabled_baseline_foreign_owner_body_and_antennas_are_rejected() {
        let mut io=fake();let gate=io.gate.clone();let mut engine=Engine::default();io.torque=true;
        assert!(engine.pin_enable(&mut io,&gate,"owner").is_err());assert!(!io.log.contains(&"enable"));
        io.torque=false;engine.pin_enable(&mut io,&gate,"owner").unwrap();
        for n in [0,7,8] {let mut target=[0.;9];target[n]=0.001;assert!(engine.goals(&mut io,&gate,"owner",target).is_err());}
        assert!(engine.goals(&mut io,&gate,"foreign",[0.;9]).is_err());
    }
    #[test] fn stop_ack_alone_and_unknown_serial_do_not_prove_cleanup() {
        let mut io=fake();let mut engine=Engine::default();let start=Some(Instant::now());engine.stop_tick(&mut io,start);assert!(!engine.stop_known());
        std::thread::sleep(Duration::from_millis(51));engine.stop_tick(&mut io,start);assert!(!engine.stop_known());
        std::thread::sleep(Duration::from_millis(51));engine.stop_tick(&mut io,start);assert!(engine.stop_known());
        io.positions[1]=0.01;engine.stop_tick(&mut io,start);assert!(!engine.stop_known());
        let mut engine=Engine::default();io.fail_disable=true;engine.stop_tick(&mut io,start);assert!(!engine.stop_known());
        let mut engine=Engine::default();io.fail_disable=false;engine.stop_tick(&mut io,Some(Instant::now()-Duration::from_millis(501)));
        assert!(!engine.stop_known()); // delayed actual stop cannot relabel its start
    }
    #[test] fn expired_action_cannot_write() {
        let mut io=fake();let gate=io.gate.clone();let mut engine=Engine::default();engine.pin_enable(&mut io,&gate,"owner").unwrap();
        gate.revoke("owner").unwrap();let before=io.log.len();assert!(engine.goals(&mut io,&gate,"owner",[0.;9]).is_err());assert_eq!(before,io.log.len());
    }
    #[test] fn delayed_serial_read_cannot_relabel_source_or_enable() {
        let mut io=fake();io.delay=Duration::from_millis(102);let gate=io.gate.clone();let mut engine=Engine::default();
        assert!(engine.pin_enable(&mut io,&gate,"owner").is_err());assert!(!io.log.contains(&"enable"));assert!(engine.latest.is_none());
        engine.stop_tick(&mut io,Some(Instant::now()));assert!(!engine.stop_known());assert!(engine.latest.is_none());
    }
    #[test] fn infinite_producer_cannot_starve_priority_stop_or_make_purge_unbounded() {
        let mut io=fake();let priority=io.priority.clone();let mut engine=Engine::default();let mut count=0;
        engine.stop_before_bounded_purge(&mut io,Some(Instant::now()),|| {
            assert!(priority.load(std::sync::atomic::Ordering::SeqCst));count+=1;true // never empty
        });
        assert_eq!(count,100);assert_eq!(io.log[0],"disable");
    }
}
