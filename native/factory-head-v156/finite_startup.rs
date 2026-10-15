//! Irreversible process-local opt-in before any controller; no startup writes.
use std::sync::{Mutex,atomic::{AtomicU8,Ordering}};
use std::time::{Duration,Instant};

pub struct StartupLatch(AtomicU8); // 0 virgin, 1 prepared, 2 legacy, 3 finite claimed
impl StartupLatch {
    pub const fn new()->Self {Self(AtomicU8::new(0))}
    pub fn prepare(&self)->Result<(),String> {
        self.0.compare_exchange(0,1,Ordering::SeqCst,Ordering::SeqCst).map(|_|()).map_err(|_|"fresh native process required".into())
    }
    pub fn claim_legacy(&self)->Result<(),String> {
        match self.0.compare_exchange(0,2,Ordering::SeqCst,Ordering::SeqCst) {
            Ok(_)|Err(2)=>Ok(()),_=>Err("finite startup forbids another controller".into())
        }
    }
    pub fn claim(&self)->Result<bool,String> {
        loop {
            match self.0.load(Ordering::SeqCst) {
                0=>if self.0.compare_exchange(0,2,Ordering::SeqCst,Ordering::SeqCst).is_ok(){return Ok(false)},
                1=>if self.0.compare_exchange(1,3,Ordering::SeqCst,Ordering::SeqCst).is_ok(){return Ok(true)},
                2=>return Ok(false),_=>return Err("finite constructor already consumed".into())
            }
        }
    }
    pub fn requested(&self)->bool {matches!(self.0.load(Ordering::SeqCst),1|3)}
}
pub static PROCESS:StartupLatch=StartupLatch::new();
#[derive(Clone,Default)]
pub struct Receipt {pub complete:bool,pub reads:u64,pub health:Vec<u8>,pub torque:Vec<bool>,pub elapsed_ms:f64}
pub static RECEIPT:Mutex<Option<Receipt>>=Mutex::new(None);
pub trait ReadOnlyIo {fn read(&mut self,id:u8,address:u8,length:u8)->Result<Vec<u8>,String>;}
pub struct Initial {pub positions:[f64;9],pub mode:u8}

pub fn ordinary_allowed(command:&super::MotorCommand)->bool {
    matches!(command,super::MotorCommand::ReadRawBytes { id:10..=18,addr,length,.. }
        if matches!((*addr,*length),(0,2)|(64,1)|(70,1)|(132,4)|(144,2)|(146,1)|(11,1)))
}

pub fn check<T:ReadOnlyIo>(io:&mut T)->Result<Initial,String> {
    let began=Instant::now();let mut receipt=Receipt::default();
    let result=(|| {
        let mut positions=[0.;9];let mut mode=0;
        for (address,length) in [(0,2),(70,1),(144,2),(146,1),(64,1),(11,1),(132,4)] {
            let group=Instant::now();
            for n in 0..9 {
                if began.elapsed()>Duration::from_secs(1) || group.elapsed()>Duration::from_millis(100) {return Err("readonly startup budget exceeded".into())}
                receipt.reads+=1;
                let before=Instant::now();let bytes=io.read(10+n as u8,address,length)?;
                if bytes.len()!=length as usize || before.elapsed()>Duration::from_millis(25)
                    || group.elapsed()>Duration::from_millis(100) || began.elapsed()>Duration::from_secs(1) {return Err("readonly startup read unknown/stale".into())}
                match address {
                    0=>if u16::from_le_bytes([bytes[0],bytes[1]])!=if n<7 {1200}else{1190} {return Err("readonly motor model mismatch".into())},
                    70=>{receipt.health.push(bytes[0]);if !matches!(bytes[0],0|1){return Err("readonly startup rejects hardware fault without reboot".into())}},
                    144=>if !(68..=76).contains(&u16::from_le_bytes([bytes[0],bytes[1]])){return Err("readonly wireless voltage profile mismatch".into())},
                    146=>if bytes[0]>=45 {return Err("readonly startup temperature profile mismatch".into())},
                    64=>{receipt.torque.push(bytes[0]!=0);if bytes[0]!=0{return Err("readonly startup requires all-nine disabled torque".into())}},
                    11=>{if n==1 {mode=bytes[0]}},
                    132=>{positions[n]=i32::from_le_bytes([bytes[0],bytes[1],bytes[2],bytes[3]]) as f64*(2.*std::f64::consts::PI/4096.)-std::f64::consts::PI;
                        if positions[n].abs()>4.*std::f64::consts::PI{return Err("readonly startup position bound".into())}},
                    _=>unreachable!()
                }
            }
        }
        receipt.complete=true;Ok(Initial {positions,mode})
    })();
    receipt.elapsed_ms=began.elapsed().as_secs_f64()*1000.;
    if let Ok(mut target)=RECEIPT.lock(){*target=Some(receipt)}
    result
}

#[cfg(test)] mod tests {
    use super::*;
    struct Fake {calls:Vec<(u8,u8,u8)>,fault:bool,torque:bool,delay:bool}
    impl ReadOnlyIo for Fake {
        fn read(&mut self,id:u8,address:u8,length:u8)->Result<Vec<u8>,String>{
            self.calls.push((id,address,length));if self.delay {std::thread::sleep(Duration::from_millis(26))}
            Ok(match address {0=>(if id<17 {1200u16}else{1190u16}).to_le_bytes().to_vec(),
                70=>vec![if self.fault {4}else{1}],144=>72u16.to_le_bytes().to_vec(),146=>vec![30],
                64=>vec![if self.torque && id==18 {1}else{0}],11=>vec![3],132=>2048i32.to_le_bytes().to_vec(),_=>panic!("write/unreviewed transaction")})
        }
    }
    fn fake()->Fake {Fake {calls:vec![],fault:false,torque:false,delay:false}}
    #[test] fn prepared_constructor_is_single_use_and_sync_controller_is_denied() {
        let gate=StartupLatch::new();gate.prepare().unwrap();assert!(gate.claim_legacy().is_err());assert!(gate.claim().unwrap());
        assert!(gate.prepare().is_err());assert!(gate.claim().is_err());assert!(gate.claim_legacy().is_err());
        let gate=StartupLatch::new();gate.claim_legacy().unwrap();assert!(gate.prepare().is_err());assert!(!gate.claim().unwrap());assert!(!gate.claim().unwrap());
    }
    #[test] fn prearm_ordinary_mutators_pid_and_raw_reboot_packets_are_denied() {
        use super::super::MotorCommand;
        for command in [MotorCommand::EnableTorque(),MotorCommand::DisableTorque(),
            MotorCommand::SetBodyRotation {position:0.},MotorCommand::SetAntennasPositions {positions:[0.;2]},
            MotorCommand::SetStewartPlatformOperatingMode {mode:3},
            MotorCommand::WriteRawBytes {id:17,addr:80,data:vec![0;6]},
            MotorCommand::WriteRawPacket {packet:vec![0xff,0xff,0xfd],tx:std::sync::mpsc::channel().0},
            MotorCommand::FiniteEnable {owner:"unknown".into(),action:"x".into()}] {
            assert!(!ordinary_allowed(&command));
        }
        assert!(ordinary_allowed(&MotorCommand::ReadRawBytes {id:17,addr:70,length:1,tx:std::sync::mpsc::channel().0}));
        assert!(!ordinary_allowed(&MotorCommand::ReadRawBytes {id:19,addr:70,length:1,tx:std::sync::mpsc::channel().0}));
        assert!(!ordinary_allowed(&MotorCommand::ReadRawBytes {id:17,addr:80,length:6,tx:std::sync::mpsc::channel().0}));
    }
    #[test] fn healthy_readonly_profile_contains_only_fixed_reads_and_no_reboot_or_mutators() {
        let mut io=fake();let sample=check(&mut io).unwrap();assert_eq!(io.calls.len(),63);assert_eq!(sample.positions,[0.;9]);assert_eq!(sample.mode,3);
        for (_,a,l) in io.calls {assert!(matches!((a,l),(0,2)|(70,1)|(144,2)|(146,1)|(64,1)|(11,1)|(132,4)))}
    }
    #[test] fn fault_partial_torque_or_delayed_read_fail_without_retry_or_reboot() {
        let mut io=fake();io.fault=true;assert!(check(&mut io).is_err());assert_eq!(io.calls.len(),10);
        let mut io=fake();io.torque=true;assert!(check(&mut io).is_err());assert_eq!(io.calls.len(),45);
        let mut io=fake();io.delay=true;assert!(check(&mut io).is_err());assert_eq!(io.calls.len(),1);
    }
}
