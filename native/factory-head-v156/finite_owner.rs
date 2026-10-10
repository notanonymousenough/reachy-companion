//! Process-local, single-use finite ownership. No UART or Python dependency.
use std::sync::Mutex;
use std::time::{Duration, Instant};

pub struct FiniteOwner { state: Mutex<Option<State>> }
struct State { owner: String, deadline: Instant, policy_until: Instant, revoked: bool }
impl FiniteOwner {
    pub fn new() -> Self { Self { state: Mutex::new(None) } }
    pub fn arm(&self, owner: &str, duration_ms: u64, policy_ms: u64) -> Result<(), &'static str> {
        if owner.is_empty() || owner.len()>256 || !(4000..=12000).contains(&duration_ms) || !(1..=300).contains(&policy_ms) { return Err("invalid finite binding"); }
        let mut state=self.state.lock().map_err(|_| "owner poisoned")?;
        if state.is_some() { return Err("finite owner cannot rearm"); }
        let now=Instant::now();
        *state=Some(State { owner:owner.into(),deadline:now+Duration::from_millis(duration_ms),policy_until:now+Duration::from_millis(policy_ms),revoked:false });
        Ok(())
    }
    pub fn sealed(&self) -> bool { self.state.lock().map(|s| s.is_some()).unwrap_or(true) }
    pub fn withdrawn(&self) -> bool {
        let Ok(mut state)=self.state.lock() else { return true };
        let Some(state)=state.as_mut() else { return false };
        if Instant::now()>=state.deadline || Instant::now()>=state.policy_until { state.revoked=true; }
        state.revoked
    }
    pub fn admit(&self, owner:&str) -> bool {
        if self.withdrawn() { return false }
        self.state.lock().map(|s| s.as_ref().is_some_and(|s| s.owner==owner && !s.revoked && Instant::now()<s.deadline && Instant::now()<s.policy_until)).unwrap_or(false)
    }
    pub fn refresh(&self, owner:&str, remaining_ms:u64) -> Result<(), &'static str> {
        if !(1..=300).contains(&remaining_ms) || self.withdrawn() { return Err("withdrawn/stale policy"); }
        let mut state=self.state.lock().map_err(|_| "owner poisoned")?;
        let state=state.as_mut().ok_or("unarmed")?;
        if state.owner!=owner { return Err("foreign owner") }
        if state.revoked || Instant::now()>=state.deadline || Instant::now()>=state.policy_until { state.revoked=true;return Err("owner/expiry mismatch") }
        state.policy_until=Instant::now()+Duration::from_millis(remaining_ms);Ok(())
    }
    pub fn revoke(&self, owner:&str) -> Result<(), &'static str> {
        let mut state=self.state.lock().map_err(|_| "owner poisoned")?;
        let state=state.as_mut().ok_or("unarmed")?;
        if state.owner!=owner { return Err("foreign owner") }
        state.revoked=true;Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    #[test] fn foreign_owner_and_rearm_are_denied() {
        let gate=FiniteOwner::new();gate.arm("owned",4000,300).unwrap();
        assert!(!gate.admit("foreign"));assert!(gate.revoke("foreign").is_err());assert!(gate.refresh("foreign",300).is_err());assert!(gate.admit("owned"));
        gate.revoke("owned").unwrap();assert!(!gate.admit("owned"));
        assert!(gate.refresh("owned",300).is_err());assert!(gate.arm("new",4000,300).is_err());
    }
    #[test] fn queued_work_is_checked_at_execution_and_not_revived() {
        let gate=FiniteOwner::new();gate.arm("owned",4000,1).unwrap();
        let queued_owner="owned";std::thread::sleep(Duration::from_millis(4));
        assert!(!gate.admit(queued_owner));assert!(gate.withdrawn());assert!(gate.refresh(queued_owner,300).is_err());
    }
    #[test] fn revoke_does_not_wait_for_an_occupied_ordinary_queue() {
        let gate=Arc::new(FiniteOwner::new());gate.arm("owned",4000,300).unwrap();
        let (tx,rx)=std::sync::mpsc::sync_channel::<u8>(1);tx.send(1).unwrap();
        let blocked=std::thread::spawn(move || tx.send(2));
        gate.revoke("owned").unwrap();assert!(gate.withdrawn());assert!(!gate.admit("owned"));
        assert_eq!(rx.recv().unwrap(),1);blocked.join().unwrap().unwrap();
    }
    #[test] fn absolute_deadline_cannot_be_extended_by_policy_refresh() {
        let gate=FiniteOwner::new();gate.arm("owned",4000,300).unwrap();
        // Move only the absolute clock to expiry; policy remains otherwise live.
        gate.state.lock().unwrap().as_mut().unwrap().deadline=Instant::now();
        assert!(gate.refresh("owned",300).is_err());assert!(!gate.admit("owned"));
    }
    #[test] fn poisoned_state_fails_closed() {
        let gate=Arc::new(FiniteOwner::new());let other=gate.clone();
        let _=std::thread::spawn(move || { let _held=other.state.lock().unwrap();panic!("fault"); }).join();
        assert!(gate.sealed());assert!(gate.withdrawn());assert!(!gate.admit("owned"));
    }
}
