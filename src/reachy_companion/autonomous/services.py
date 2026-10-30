"""Background IO slots for the existing Scheduler; never an independent agent."""
import json
import time
from .runtime import Job
from .contracts import uid, Task, decode
from .state import utc


class Services:
    def __init__(self, scheduler, store, sensors=None, deliveries=None, tools=None):
        self.scheduler=scheduler;self.store=store;self.last_depth=0;self.unresolved=store.tool_pending()
        self.sensors=sensors or {};self.deliveries=deliveries or {};self.tools=tools or {}
        self.polls={};self.next_poll={};self.exports={};self.next_export={}
        self.tool_jobs={};self.maintenance=None;self.next_memory=0;self.next_character=0
        self.errors={};self.latency={};self.closed=False
        self.update_reader=None;self.update_job=None;self.next_update=0
        self.reload()
        now=time.monotonic();settings=scheduler.config.get('production',{})
        self.next_memory=now+settings.get('memory_refresh_s',60);self.next_character=now+settings.get('character_refresh_s',3600)

    def reload(self):
        revision,body=self.store.current()
        state=self.scheduler.state
        state.durable_revision=revision;state.character=body
        state.revision+=1

    def status(self):
        if not self.closed:self.last_depth=self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0]
        return dict(execution_busy=bool(self.busy()),outbox_depth=self.last_depth,
            delivery={name:('configured' if name in self.deliveries else 'unconfigured') for name in ('s3','vps')},
            errors=dict(self.errors),unresolved_tools=dict(self.unresolved),latency_s=dict(self.latency),state_revision=self.scheduler.state.durable_revision)

    def log(self,event):
        if not self.scheduler.state.privacy:
            self.store.append(event, destinations=('s3','vps') if self.scheduler.config['export_enabled'] else ())

    def busy(self):
        jobs=list(self.polls.values())+list(self.exports.values())+list(self.tool_jobs.values())
        if self.maintenance:jobs.append(self.maintenance)
        if self.update_job:jobs.append(self.update_job)
        return sum(not row[0].future.done() for row in jobs)

    def update(self,patch,expected,reason,now,origin='agent'):
        state=self.scheduler.state
        if state.privacy or state.stopped:raise ValueError('Update admission withdrawn')
        if not isinstance(patch,dict):raise ValueError('Update object required')
        settings=self.scheduler.config.get('production',{})
        for field in patch:
            cadence=settings.get('character_refresh_s',3600) if field in ('personality','principles') else settings.get('memory_refresh_s',60) if field=='memory' else 0
            if cadence and time.time()-self.store.last_changed(field)<cadence:raise ValueError('Update cadence not due')
        if 'goal' in patch:
            text=patch['goal']
            if not isinstance(text,str) or len(text)>512:raise ValueError('Goal text bound')
            old=state.character.get('goal')
            patch={**patch,'goal':dict(id=old['id'] if old else uid(),
                version=old['version']+1 if old else 0,text=text,changed_at=utc(),
                reason=reason,evidence_ids=[],origin=origin)}
        self.store.update(patch,expected,reason);self.reload()
        state.record('state_updated')

    def start_tool(self, name, argument, binding, now):
        state=self.scheduler.state
        if (name not in self.tools or state.privacy or state.stopped or state.overload!='ACTIVE'
                or len(self.tool_jobs)>=2 or name in self.tool_jobs or name in self.unresolved):
            state.record('tool_admission_rejected');return
        request=dict(argument=argument,request_id=uid(),authority=binding.authority.wire(),ttl_ms=5000)
        self.store.tool_begin(name,request['request_id']);self.unresolved[name]=request['request_id']
        self.tool_jobs[name]=(Job(self.tools[name],request),now,state.authority)
        state.record('tool_started')

    def advance(self,now):
        state=self.scheduler.state
        self.unresolved=self.store.tool_pending()
        if self.store.current()[0]!=state.durable_revision:self.reload()
        # All callbacks return values to this owner; IO threads never mutate State/SQLite.
        for name,(job,started,authority) in list(self.polls.items()):
            if not job.future.done():continue
            try:
                event=job.future.result()
                if authority!=state.authority or state.privacy:raise ValueError('Sensor authority changed')
                event={**event,'type':'sensor','id':name,'source_id':self.sensors[name][2]}
                event['age_ms']=event.get('age_ms',0)+max(0,int((now-started)*1000))
                self.scheduler.ingest(event,now)
                self.latency[name]=now-started
            except Exception as exc:self.errors[name]=type(exc).__name__
            del self.polls[name]
        for name,(job,started,authority) in list(self.tool_jobs.items()):
            if not job.future.done():continue
            try:
                result=job.future.result()
                self.store.tool_terminal(name,self.unresolved[name]);self.unresolved.pop(name)
                if authority==state.authority and not state.privacy:
                    text=json.dumps(result,ensure_ascii=False,allow_nan=False)
                    if len(text)>2048:raise ValueError('Tool result bound')
                    state.tool_results[name]=text
                    state.previous.append('tool '+name+': '+text[:96])
                    state.record('tool_completed')
            except Exception as exc:self.errors['tool:'+name]=type(exc).__name__
            self.latency['tool:'+name]=now-started;del self.tool_jobs[name]
        for destination,(job,started,event_id) in list(self.exports.items()):
            if not job.future.done():continue
            try:
                if job.future.result()!=event_id:raise ValueError('Wrong export acknowledgement')
                self.store.ack(destination,event_id);self.errors.pop(destination,None)
            except Exception as exc:self.errors[destination]=type(exc).__name__
            del self.exports[destination];self.next_export[destination]=now+(2 if destination in self.errors else 0)
        if self.maintenance and self.maintenance[0].future.done():
            job,started,authority,revision,character=self.maintenance
            try:
                result=job.future.result()
                if authority!=state.authority or result.get('compute_boot_id')!=authority.compute_boot_id or result.get('request_id')!=self.maintenance_task.attempt_id:raise ValueError('Maintenance authority changed')
                patch=decode(result['output'])
                if set(patch)-({'personality','principles'} if character else {'memory'}):raise ValueError('Maintenance capability')
                self.update(patch,revision,'periodic reflection (model inference)',now)
                self.errors.pop('maintenance',None)
            except Exception as exc:self.errors['maintenance']=type(exc).__name__
            # Cadence is measured from completion, just like last_changed in
            # the durable store; slow inference must not make the next update early.
            if character:self.next_character=now+self.scheduler.config.get('production',{}).get('character_refresh_s',3600)
            else:self.next_memory=now+self.scheduler.config.get('production',{}).get('memory_refresh_s',60)
            self.maintenance=None
        if self.update_job and self.update_job[0].future.done():
            job,started,authority=self.update_job
            try:
                proposal=job.future.result()
                if proposal is not None:
                    if (authority!=state.authority or now-started>5 or set(proposal)!={'patch','expected_revision','reason'}):
                        raise ValueError('Stale/invalid VPS update')
                    self.update(proposal['patch'],proposal['expected_revision'],proposal['reason'],now)
            except Exception as exc:self.errors['updates']=type(exc).__name__
            self.update_job=None;self.next_update=now+60
        if self.closed or state.privacy or state.stopped:return
        if self.update_reader and not self.update_job and now>=self.next_update and state.overload=='ACTIVE':
            self.update_job=(Job(self.update_reader),now,state.authority)
        for name,(poll,period,source) in (self.sensors.items() if state.overload=='ACTIVE' else ()):
            if state.muted and name.startswith('audio'):continue
            if name not in self.polls and now>=self.next_poll.get(name,0):
                self.polls[name]=(Job(poll),now,state.authority);self.next_poll[name]=now+period
        for destination,send in self.deliveries.items():
            if destination not in self.exports and now>=self.next_export.get(destination,0):
                item=self.store.pending(destination)
                if item:self.exports[destination]=(Job(send,*item),now,item[0])
        if (state.overload!='ACTIVE' or self.maintenance or self.scheduler.main_job
                or any(not k.startswith('autonomous:') for k in state.candidates) or any(t.status=='ready' for t in state.tasks.values())):return
        character=now>=self.next_character
        if not character and now<self.next_memory:return
        if character:self.next_character=now+self.scheduler.config.get('production',{}).get('character_refresh_s',3600)
        else:self.next_memory=now+self.scheduler.config.get('production',{}).get('memory_refresh_s',60)
        # Same main model/permit, bounded context; reflections are explicitly inferences.
        prompt=dict(schema_version='companion-1',
            utterance='Return ONLY JSON patch '+('personality/principles (strings <=512)' if character else 'memory (inference summary string <=2048)'),
            state=dict(maintenance='character' if character else 'memory',current=state.character,recent=list(state.previous),historical_working=dict(state.working)),memory=[],observations=[])
        task=Task(uid(),uid(),'maintenance',prompt,state.authority,now,now+30)
        self.maintenance_task=task
        self.maintenance=(Job(self.scheduler.gateway.main,task),now,state.authority,state.durable_revision,character)

    def close(self):
        self.status()
        self.closed=True
        # Occupied transports remain visible; do not certify cancellation or close
        # the database under a callback (callbacks never access it).
        self.store.close()
