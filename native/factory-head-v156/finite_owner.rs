//! Single-use ownership with ORIGINAL absolute same-host monotonic deadlines.
use std::sync::{Arc,Mutex};
use std::sync::atomic::{AtomicBool,Ordering};
use std::time::{Duration,Instant};

pub fn monotonic_ns()->Result<u64,&'static str> {
    #[cfg(target_os="linux")]
    {
        let mut ts=libc::timespec { tv_sec:0,tv_nsec:0 };
        if unsafe {libc::clock_gettime(libc::CLOCK_MONOTONIC,&mut ts)}!=0 || ts.tv_sec<0 || !(0..1_000_000_000).contains(&ts.tv_nsec) { return Err("monotonic clock unavailable") }
        (ts.tv_sec as u64).checked_mul(1_000_000_000).and_then(|n| n.checked_add(ts.tv_nsec as u64)).ok_or("monotonic overflow")
    }
    #[cfg(all(test,not(target_os="linux")))]
    { static ORIGIN:std::sync::OnceLock<Instant>=std::sync::OnceLock::new();Ok(ORIGIN.get_or_init(Instant::now).elapsed().as_nanos() as u64) }
    #[cfg(all(not(test),not(target_os="linux")))]
    { Err("finite authority requires Linux CLOCK_MONOTONIC") }
}

type Clock=Arc<dyn Fn()->Result<u64,&'static str>+Send+Sync>;
pub struct FiniteOwner { state:Mutex<Option<State>>,clock:Clock,clock_failed:AtomicBool }
struct State { owner:String,deadline:u64,policy_until:u64,revoked:bool,withdrawn_at:Option<u64>,clock_failed:bool }
impl FiniteOwner {
    pub fn new()->Self {Self {state:Mutex::new(None),clock:Arc::new(monotonic_ns),clock_failed:AtomicBool::new(false)}}
    fn read_clock(&self)->Result<u64,&'static str> {
        if self.clock_failed.load(Ordering::SeqCst) {return Err("authority clock permanently quarantined")}
        match (self.clock)() {
            Ok(value)=>Ok(value),
            Err(error)=>{self.clock_failed.store(true,Ordering::SeqCst);Err(error)}
        }
    }
    #[cfg(test)] pub fn arm(&self,owner:&str,duration_ms:u64,policy_ms:u64)->Result<(),&'static str> {
        let now=self.read_clock()?;
        self.arm_at(owner,now.checked_add(duration_ms*1_000_000).ok_or("overflow")?,now.checked_add(policy_ms*1_000_000).ok_or("overflow")?)
    }
    #[cfg(test)] pub fn refresh(&self,owner:&str,remaining_ms:u64)->Result<(),&'static str> {
        self.refresh_at(owner,self.read_clock()?.checked_add(remaining_ms*1_000_000).ok_or("overflow")?)
    }
    pub fn arm_at(&self,owner:&str,deadline:u64,policy_until:u64)->Result<(),&'static str> {
        let mut state=self.state.lock().map_err(|_| "owner poisoned")?;
        let now=self.read_clock()?; // AFTER any native entry and mutex delay
        let absolute=deadline.checked_sub(now).ok_or("expired absolute authority")?;
        let policy=policy_until.checked_sub(now).ok_or("expired policy authority")?;
        if owner.is_empty() || owner.len()>256 || !(1..=12_000_000_000).contains(&absolute) || !(1..=300_000_000).contains(&policy) {return Err("invalid absolute finite binding")}
        if state.is_some() {return Err("finite owner cannot rearm")}
        *state=Some(State {owner:owner.into(),deadline,policy_until,revoked:false,withdrawn_at:None,clock_failed:false});Ok(())
    }
    pub fn sealed(&self)->bool {self.clock_failed.load(Ordering::SeqCst) || self.state.lock().map(|s| s.is_some()).unwrap_or(true)}
    fn expire(state:&mut State,now:u64) {
        let expiry=state.deadline.min(state.policy_until);
        if now>=expiry {state.revoked=true;state.withdrawn_at.get_or_insert(expiry);}
    }
    pub fn withdrawn(&self)->bool {
        if self.clock_failed.load(Ordering::SeqCst) {return true}
        let Ok(mut state)=self.state.lock() else {return true};
        let Some(state)=state.as_mut() else {return false};
        match self.read_clock() {Ok(now)=>Self::expire(state,now),Err(_)=>{state.revoked=true;state.clock_failed=true}}
        state.revoked
    }
    pub fn withdrawn_at(&self)->Option<Instant> {
        // Instant is used only for an intentionally CONSERVATIVE proof bound.
        // Capture it BEFORE any mutex/clock delay; subtraction cannot extend SLA.
        let before=Instant::now();self.withdrawn();
        let original={let state=self.state.lock().ok()?;let state=state.as_ref()?;if state.clock_failed {return None} state.withdrawn_at?};
        let elapsed=self.read_clock().ok()?.checked_sub(original)?;
        before.checked_sub(Duration::from_nanos(elapsed))
    }
    pub fn authority_age_ns(&self)->Option<u64> {
        self.withdrawn();let original={let state=self.state.lock().ok()?;let state=state.as_ref()?;if state.clock_failed {return None} state.withdrawn_at?};
        self.read_clock().ok()?.checked_sub(original)
    }
    pub fn admit(&self,owner:&str)->bool {
        let Ok(mut state)=self.state.lock() else {return false};
        let Some(state)=state.as_mut() else {return false};
        let Ok(now)=self.read_clock() else {state.revoked=true;state.clock_failed=true;return false};
        Self::expire(state,now);state.owner==owner && !state.revoked
    }
    pub fn refresh_at(&self,owner:&str,policy_until:u64)->Result<(),&'static str> {
        let mut state=self.state.lock().map_err(|_| "owner poisoned")?;
        let state=state.as_mut().ok_or("unarmed")?;
        if state.owner!=owner {return Err("foreign owner")}
        let now=match self.read_clock() {Ok(now)=>now,Err(error)=>{state.revoked=true;state.clock_failed=true;return Err(error)}};
        Self::expire(state,now);
        if state.revoked {return Err("withdrawn policy")}
        let remaining=policy_until.checked_sub(now).ok_or("expired policy request")?;
        if !(1..=300_000_000).contains(&remaining) {return Err("invalid policy request")}
        state.policy_until=policy_until;Ok(()) // copy ORIGINAL deadline; never now + remaining
    }
    pub fn revoke(&self,owner:&str)->Result<(),&'static str> {
        let mut state=self.state.lock().map_err(|_| "owner poisoned")?;
        let state=state.as_mut().ok_or("unarmed")?;
        if state.owner!=owner {return Err("foreign owner")}
        state.revoked=true;
        let now=match self.read_clock() {Ok(now)=>now,Err(error)=>{state.clock_failed=true;return Err(error)}};
        state.withdrawn_at.get_or_insert(now.min(state.deadline.min(state.policy_until)));Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64,Ordering};
    fn synthetic()->(Arc<FiniteOwner>,Arc<AtomicU64>) {
        let now=Arc::new(AtomicU64::new(10_000_000_000));let clock=now.clone();
        (Arc::new(FiniteOwner {clock_failed:AtomicBool::new(false),state:Mutex::new(None),clock:Arc::new(move ||Ok(clock.load(Ordering::SeqCst)))}),now)
    }
    #[test] fn foreign_owner_and_rearm_are_denied() {
        let gate=FiniteOwner::new();gate.arm("owned",4001,300).unwrap();
        assert!(!gate.admit("foreign"));assert!(gate.revoke("foreign").is_err());assert!(gate.refresh("foreign",300).is_err());assert!(gate.admit("owned"));
        gate.revoke("owned").unwrap();assert!(!gate.admit("owned"));assert!(gate.refresh("owned",300).is_err());assert!(gate.arm("new",4001,300).is_err());
    }
    #[test] fn queued_work_is_checked_at_execution_and_not_revived() {
        let gate=FiniteOwner::new();gate.arm("owned",4001,1).unwrap();std::thread::sleep(Duration::from_millis(4));
        assert!(!gate.admit("owned"));assert!(gate.withdrawn());assert!(gate.refresh("owned",300).is_err());
    }
    #[test] fn revoke_does_not_wait_for_an_occupied_ordinary_queue() {
        let gate=Arc::new(FiniteOwner::new());gate.arm("owned",4001,300).unwrap();let (tx,rx)=std::sync::mpsc::sync_channel::<u8>(1);tx.send(1).unwrap();
        let blocked=std::thread::spawn(move ||tx.send(2));gate.revoke("owned").unwrap();assert!(gate.withdrawn());assert!(!gate.admit("owned"));assert_eq!(rx.recv().unwrap(),1);blocked.join().unwrap().unwrap();
    }
    #[test] fn absolute_deadline_cannot_be_extended_by_policy_refresh() {
        let (gate,now)=synthetic();gate.arm_at("owned",14_000_000_000,10_300_000_000).unwrap();
        gate.state.lock().unwrap().as_mut().unwrap().deadline=10_001_000_000;now.store(10_002_000_000,Ordering::SeqCst);
        assert!(gate.refresh_at("owned",10_302_000_000).is_err());assert!(!gate.admit("owned"));
    }
    #[test] fn native_entry_delay_copies_original_deadlines_and_rejects_expired_requests() {
        let (gate,now)=synthetic();now.store(10_200_000_000,Ordering::SeqCst);
        gate.arm_at("owned",22_000_000_000,10_300_000_000).unwrap();
        assert_eq!(gate.state.lock().unwrap().as_ref().unwrap().policy_until,10_300_000_000);
        now.store(10_301_000_000,Ordering::SeqCst);assert!(!gate.admit("owned"));
        assert_eq!(gate.authority_age_ns(),Some(1_000_000));
        let (gate,now)=synthetic();now.store(10_301_000_000,Ordering::SeqCst);
        assert!(gate.arm_at("owned",22_000_000_000,10_300_000_000).is_err());assert!(!gate.sealed());
    }
    #[test] fn native_mutex_delay_cannot_reanchor_refresh_or_revive_expiry() {
        let (gate,now)=synthetic();gate.arm_at("owned",22_000_000_000,10_300_000_000).unwrap();
        let held=gate.state.lock().unwrap();let other=gate.clone();
        let entered=Arc::new(std::sync::Barrier::new(2));let barrier=entered.clone();
        let worker=std::thread::spawn(move ||{barrier.wait();other.refresh_at("owned",10_400_000_000)});
        entered.wait();now.store(10_301_000_000,Ordering::SeqCst);drop(held);
        assert!(worker.join().unwrap().is_err());assert!(gate.withdrawn());assert_eq!(gate.authority_age_ns(),Some(1_000_000));
    }
    #[test] fn bad_u64_bounds_and_clock_fault_fail_closed() {
        let (gate,_)=synthetic();assert!(gate.arm_at("owned",u64::MAX,u64::MAX).is_err());assert!(gate.arm_at("owned",0,0).is_err());
        let gate=FiniteOwner {clock_failed:AtomicBool::new(false),state:Mutex::new(None),clock:Arc::new(||Err("clock failed"))};assert!(gate.arm_at("owned",1,1).is_err());
    }
    #[test] fn clock_fault_after_arm_never_relabels_unknown_withdrawal_as_later_expiry() {
        let failed=Arc::new(std::sync::atomic::AtomicBool::new(false));let fault=failed.clone();
        let now=Arc::new(AtomicU64::new(10_000_000_000));let clock=now.clone();
        let gate=FiniteOwner {clock_failed:AtomicBool::new(false),state:Mutex::new(None),clock:Arc::new(move || {
            if fault.load(Ordering::SeqCst) {Err("clock failed")} else {Ok(clock.load(Ordering::SeqCst))}
        })};
        gate.arm_at("owned",22_000_000_000,10_300_000_000).unwrap();failed.store(true,Ordering::SeqCst);
        assert!(!gate.admit("owned"));failed.store(false,Ordering::SeqCst);now.store(10_301_000_000,Ordering::SeqCst);
        assert!(gate.withdrawn());assert!(gate.authority_age_ns().is_none());assert!(gate.withdrawn_at().is_none());
    }
    fn secondary_read_fault(in_instant_getter:bool) {
        let calls=Arc::new(AtomicU64::new(0));let counter=calls.clone();
        let gate=FiniteOwner {clock_failed:AtomicBool::new(false),state:Mutex::new(None),clock:Arc::new(move || {
            let call=counter.fetch_add(1,Ordering::SeqCst)+1;
            if call==4 {Err("second proof clock read failed")} else {Ok(10_000_000_000)}
        })};
        gate.arm_at("owned",22_000_000_000,10_300_000_000).unwrap();gate.revoke("owned").unwrap();
        if in_instant_getter {assert!(gate.withdrawn_at().is_none())} else {assert!(gate.authority_age_ns().is_none())}
        assert_eq!(calls.load(Ordering::SeqCst),4);
        // The raw clock would succeed now. No subsequent getter can regain proof.
        assert!(gate.withdrawn_at().is_none());assert!(gate.authority_age_ns().is_none());assert!(!gate.admit("owned"));
        assert_eq!(calls.load(Ordering::SeqCst),4);
    }
    #[test] fn withdrawn_at_secondary_read_failure_is_permanent() {secondary_read_fault(true)}
    #[test] fn authority_age_secondary_read_failure_is_permanent() {secondary_read_fault(false)}
    #[test] fn poisoned_state_fails_closed() {
        let gate=Arc::new(FiniteOwner::new());let other=gate.clone();let _=std::thread::spawn(move ||{let _held=other.state.lock().unwrap();panic!("fault")}).join();
        assert!(gate.sealed());assert!(gate.withdrawn());assert!(!gate.admit("owned"));
    }
}
