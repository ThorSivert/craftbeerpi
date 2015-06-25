from thread import start_new_thread
from brewapp import app, socketio
from brewapp.model import db, Temperatur
from datetime import datetime, timedelta
import globalprops
import thermometer
from flask.ext.socketio import SocketIO, emit
from brewapp.model import db, Step, Temperatur, Log
import time
from views import getAsArray, nextStep
from pidypi import pidpy
from heating import setHeating
from agitator import setAgitator

## GLOBALS
current_temp = 0
target_temp = 0
current_step = None

# STEP CONTROL JOB
def stepjob():

    print "START STEP JOB"
    
    temp_count = 0
    global temp
    global target_temp
    global current_step
    while True:
        current_step = Step.query.filter_by(state='A').first()
     
        if(current_step != None):
            target_temp = current_step.temp
        else:
            target_temp = -1;
            time.sleep(1)
            continue
            
        update_step = False

        
        if(current_step != None):

            ## Switch agiator on for heating phase
            if(current_step.timer_start == None  and current_temp < current_step.temp and globalprops.pidState == True):
                setAgitator(True)

            # Target temp reached! Start Timer
            if(current_step.timer > 0 and current_step.timer_start == None and current_temp >= current_step.temp):
                print "START TIMER"

                # stop the agiator if target temp reached
                if(globalprops.pidState == True):
                    setAgitator(False)
                
                current_step.timer_start = datetime.utcnow()
                db.session.add(current_step)
                db.session.commit()
                update_step = True
                

            if(current_step.type == 'A' and current_step.timer_start != None):
                # check if timer elapsed
                end = current_step.timer_start + timedelta(minutes=current_step.timer)
                now = datetime.utcnow()
                if(end < now):
                    print "NEXT STEP"
                    update_step = True
                    nextStep()

        ## Push steps to connected clients
        if(update_step == True):
            socketio.emit('steps', getAsArray(Step), namespace ='/brew')

        time.sleep( 1 )

## READ TEMP JOB 
def tempjob():
    print "START TEMP JOB"
    global current_temp
    while True:
        current_temp = thermometer.tempData1Wire(globalprops.tempSensorId)
        t = Temperatur()
        t.name1 = "P1"
        t.time = datetime.utcnow()
        t.value1 = current_temp
        
        ## Save temperatur in database
        db.session.add(t)
        db.session.commit()
    
        ## push temperatur update to all connected clients
        socketio.emit('temp', {'temp': t.value1, 'time': t.to_unixTime(t.time)}, namespace='/brew')
        time.sleep( 5 )

## PID JOB 
##
def pidjob():
    print "START PID"
    global current_temp
    global target_temp
    global current_step

    pid = pidpy(globalprops.pid_interval,globalprops.pipP,globalprops.pidI,globalprops.pidD)

    while True:
        ## PID NOT or no current step ACTIVE SKIP
        if(globalprops.pidState == False or current_step == None):
            time.sleep(1)
            continue

        # hysteresis 
        # if the temp is to below the target temp. heating 100 % on
        # PID Not needed
        #if(current_temp < target_temp - globalprops.hysteresis_min):
        #    setHeating(True)
        #    time.sleep(globalprops.pid_interval)
        #    continue

        ## Calculate heating
        heat_percent = pid.calcPID_reg4(current_temp, target_temp, True)
        heating_time = globalprops.pid_interval * heat_percent / 100
        wait_time = globalprops.pid_interval - heating_time
        ## HEATING ON
        setHeating(True)
        time.sleep(heating_time)
        ## HEATING OFF
        setHeating(False)
        time.sleep(wait_time)


## Start the theads in background
start_new_thread(tempjob,())
start_new_thread(stepjob,())
start_new_thread(pidjob,())
