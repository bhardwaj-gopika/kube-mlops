#!/usr/bin/env python3
"""
Python Script for VIMIN autotune ACL using acsys-py

Author(s): Gopika Bhardwaj, Fermilab;
"""
import logging
from sys import stdout
from time import sleep

import acsys.dpm
import acsys.sync
from acsys.dpm import ItemData

acsys_logger = logging.getLogger("acsys")
logger = logging.getLogger(__name__)
acsys_logger.setLevel("WARN")
logger.setLevel("INFO")
handler = logging.StreamHandler(stdout)
acsys_logger.addHandler(handler)
logger.addHandler(handler)

a1 = b1 = c1 = 0
a0 = b0 = c0 = 0
maxs06 = maxs12 = max125 = maxs13 = 0
limit = 0


def general_getter(parameter):
    async def wrapper(con):
        async with acsys.dpm.DPMContext(con) as dpm:
            await dpm.add_entry(0, drf=f"{parameter}@I")
            await dpm.start()
            async for evt_res in dpm:
                if isinstance(evt_res, ItemData):
                    return evt_res.data

                return None

    return acsys.run_client(wrapper)


def general_setter(parameter, value):
    async def wrapper(con):
        async with acsys.dpm.DPMContext(con) as dpm:
            await dpm.enable_settings(role="vimin_autotune_testing")
            await dpm.add_entry(0, drf=f"{parameter}.SETTING@N")
            await dpm.apply_settings([(0, value)])

    acsys.run_client(wrapper)


def general_alarm_limit(parameter):
    return general_getter(parameter=f"{parameter}.ANALOG")["maximum"] / 2


def last_event_time(event_parameter):
    two_super_cycles = 120  # seconds
    ms_in_a_sec = 1000
    duration = two_super_cycles * ms_in_a_sec

    async def wrapper(con):
        async with acsys.dpm.DPMContext(con) as dpm:
            await dpm.add_entry(0, f"{event_parameter}<-LOGGERDURATION:{duration}")
            await dpm.start()
            async for evt_res in dpm:
                if isinstance(evt_res, ItemData):
                    return evt_res.data[0]

                return None

    return acsys.run_client(wrapper)


def check_control():
    loop_status = general_getter(parameter="B:VIMLUP.STATUS")["on"]
    logger.info("B:VIMLUP is %s", loop_status)
    return loop_status


launch = check_control


def delta_set(parameter, delta):
    current = general_getter(parameter=parameter)
    general_setter(parameter=parameter, value=current + delta)
    logger.info("Old value = %s", current)
    logger.info("New value = %s", current+delta)
    


def deltaset_vimdiag(val):
    delta_set(parameter="B:VIMDIAG", delta=val)


def increment(parameter):
    delta_set(parameter, delta=1)


def events_to_list_of_strings(*events):
    return list(map(lambda x: f"e,{x:02X}", events))


def wait_on_first_event(*events):
    formatted_events = events_to_list_of_strings(*events)

    async def wrapper(con):
        # ACL version, requests.get('https://www-bd.fnal.gov/cgi-bin/acl.pl?acl=wait/event 0')
        logger.info("Waiting for first event in list of events: %s",
                    formatted_events)
        async for _ in acsys.sync.get_events(
            con, ev_str=formatted_events
        ):
            break

    acsys.run_client(wrapper)


def wait_event0():
    wait_on_first_event(0)


def check_mode():
    md = general_getter(parameter="B:VIMMOD")

    if md == 1:
        logger.info("mode = s06/s13 current")
    elif md == 2:
        logger.info("mode = s06/125 current")
    elif md == 3:
        logger.info("mode = 125/s12 current")
    elif md == -1:
        logger.info("mode = s06/s13 B:VIMTGT1")
    elif md == -2:
        logger.info("mode = s06/125 B:VIMTGT2")
    elif md == -3:
        logger.info("mode = 125/s12 B:VIMTGT3")
    elif md == 0:
        logger.info("B:VIMMOD = %s, reinitialize current mode...", md)
    else:
        if md == 9:
            logger.info("Exiting script.")
            vimlup = -1
        else:
            logger.info("B:VIMMOD = %s invalid mode.", md)
            vimlup = -2

        #general_setter(parameter="B:VIMLUP.CONTROL", value="off")
        #general_setter(parameter="B:VMLPMR.CONTROL", value="off")
        #general_setter(parameter="B:VIMLUP", value=vimlup)
        #general_setter(parameter="B:VIMMOD", value=0)
        #general_setter(parameter="B:VMDMIR", value=0)

    return md


def diag_from_mode(mode, diag):
    if mode not in [-3, -2, -1, 0, 1, 2, 3, 9]:
        diag += 100000

    return diag


def q_check2(event_ten, event_fifty_three, diag, norm125, norms06, norms12, norms13, mbtt):
    runtest = 3
    mnl = 1.25

    # Check normalized losses too high
    if norms06 > mnl or norms12 > mnl or norm125 > mnl or norms13 > mnl:
        runtest -= 10
        diag += 1

    # TODO: I don't think this does what is intended, at least not with what event## is providing
    # Check for missing beam events
    n10 = last_event_time(event_ten)
    n53 = last_event_time(event_fifty_three)
    rate = n53 / n10
    logger.info("Performing Q Check.")
    logger.info("$53/$10 = %s", rate)
    # general_setter(parameter="B:VIMATS", value=rate)
    if rate >= mbtt:
        logger.info("50 percent missing beam!")
        runtest -= 1
        diag += 10

    return {
        "diag": diag,
        "runtest": runtest,
    }

def get_max():

    global maxs06
    global maxs12
    global maxs13
    global max125

    # Get alarm limits
    maxs06 = general_alarm_limit(parameter="B:BLS060")
    maxs12 = general_alarm_limit(parameter="B:BLS120")
    max125 = general_alarm_limit(parameter="B:BL1250")
    maxs13 = general_alarm_limit(parameter="B:BLS130")

    return {
        "maxs06": maxs06,
        "maxs12": maxs12,
        "max125": max125,
        "maxs13": maxs13,

    }

def get_current_values():
    global variables

    s06 = general_getter(parameter=variables["bls060"])
    s12 = general_getter(parameter=variables["bls120"])
    one25 = general_getter(parameter=variables["bls130"])
    s13 = general_getter(parameter=variables["bl1250"])

    return {
        "s06": s06,
        "s12": s12,
        "one25": one25,
        "s13": s13,

    }

def initialize(variables):
    global limit
    global maxs06
    global maxs12
    global maxs13
    global max125
    global a1
    global b1
    global c1
    global a0
    global b0
    global c0
    logger.info("Initializing")
    global b_vimlup

    b_vimlup = general_getter(parameter="B:VIMLUP")
    # if b_vimlup != -9999:
    #     general_setter(parameter="B:VIMLUP", value=0)
    #     logger.info("Heartbeat counter set to 0.")

    # general_setter(parameter="B:VIMCHG", value=0)
    # sleep(1)  # TODO: Why wait?
    # general_setter(parameter="B:VIMERR", value=0)

    window = general_getter(parameter="B:VIMWIN")
    logger.info("VIMIN tuning window +/-%s", window)
    stepcut = general_getter(parameter="B:VIMSTC")
    logger.info("VIMIN tuning stepcut = %s", stepcut)
    max_change = general_getter(parameter="B:VIMMXC")
    logger.info("VIMIN tuning max change = %s", max_change)

    limit = general_getter(parameter="B:VIMLMT")
    limit_test = limit == 0

    # Get alarm limits
    maxs06, maxs12, max125, maxs13= get_max().values()

    # Get throughput and calculate beam intensity threshold
    # steady = general_getter(parameter="B:PROTNS")
    # threshold = steady * 0.9


    # Get current losses and calulate normalized values and ratios
    s06start, s12start, one25start, s13start = get_current_values().values()

    b1 = s06start / one25start  # mode 2
    a1 = s06start / s13start  # mode 1
    c1 = s12start / one25start  # mode 3

    #general_setter(parameter="B:VIMTGTA", value=a1)
    #general_setter(parameter="B:VIMTGTB", value=b1)
    #general_setter(parameter="B:VIMTGTC", value=c1)

    a0 = general_getter(parameter="B:VIMTGT1")
    # general_setter(parameter="B:VTGMR1", value=a0)
    b0 = general_getter(parameter="B:VIMTGT2")
    # general_setter(parameter="B:VTGMR2", value=b0)
    c0 = general_getter(parameter="B:VIMTGT3")
    # general_setter(parameter="B:VTGMR3", value=c0)

    # Get B:VIMIN setting and calculate tuning window
    autotune = "B:DATVI1"
    vimin = general_getter(parameter=autotune)

    # set B:VISTART vistart
    #general_setter(parameter="B:VISTART", value=vimin)
    logger.debug("vistart: %s", vimin)
    general_setter(parameter='B:DATPY', value =vimin)
    vimin_min = vimin - window
    vimin_max = vimin + window

    # set B:VIMBTT missing beam event tolerance thresohold
    mbtt = general_getter(parameter="B:VIMBTT")

    logger.info("Initialization complete")

    return {
        "vimin_min": vimin_min,
        "vimin_max": vimin_max,
        "limit_test": limit_test,
        "mbtt": mbtt,
        "vimin": vimin,
        "max_change": max_change,
        "stepcut": stepcut,
    }


def reduce_change_if_same(change, prev_change):
    """
    If the change is greater than 95% of the previous change and
    less than 105% of the previous change and the signs are opposite,
    then reduce the change by half.
    """
    # TODO: Why do we care that the signs are opposite?
    abs_change = abs(change)
    abs_prev_change = abs(prev_change)
    if (
        abs_change > 0.95 * abs_prev_change
        and abs_change < 1.05 * abs_prev_change
        and prev_change / change < 0
    ):
        logger.info("Reducing change by half.")
        return change * 0.5

    return change


def clamp(n, minn, maxn):
    """
    Limit the value of n to be between minn and maxn, inclusive.

    Args:

        n (float): The value to clamp.
        minn (float): The minimum value.
        maxn (float): The maximum value.

    Returns:

        float: The clamped value.
    """
    return max(min(float(maxn), float(n)), float(minn))


def vimax_clamp(change, max_change):
    """
    Meant for vimax clamping, but is a simple version of clamp.
    This considers the minimum to be the negative of the maximum.

    Args:

            change (float): The value to clamp.
            max_change (float): The maximum value.

    Returns:

            float: The clamped value.
    """
    return clamp(change, -max_change, max_change)

def make_autotune_update(change, max_change, runtest, prev_change, diag, delay1):
    # Make settings changes only if settings are allowed.
        # TODO: This could be a good use case for a function alias - ASK BEAU
        debug = general_getter(parameter="B:VIMDBUG")
        # TODO: What version of Python can we use? If it's 3.8, we can use the walrus operator
        """python
        if (debug := general_getter(parameter='B:VIMDBUG')) == 0:
        """
        if debug == 0:  # if B:VIMDBUG debug mode is off.

            # If change magnitude is ok and beam quality is ok, make vimin change
            # TODO: instead of evaluating change twice, we can combine comparisons
            """python
            if 0.001 <= abs(change) <= max_change and runtest == 3:
            """
            # TODO: `runtime` is always 3 or less. We only check if it's 3, it's default value. I think this can be a bool.
            # TODO: It'd be nice to name this evaluation so I don't need to understand the intent.
            if abs(change) <= max_change and abs(change) >= 0.001 and runtest == 3:
                delta_set(parameter=variables["vimin"], delta=change)
                logger.info("Adjustment made... %s", change)
                prev_change = change

                # general_setter(parameter="B:VIMCHG", value=change)
                sleep(1)  # TODO: Why wait?
                # general_setter(parameter="B:VIMERR", value=error)

                autotune = variables["vimin"]
                vimin = general_getter(parameter=autotune)
                #drift = vimin - vistart
                #general_setter(parameter="B:VIMDFT", value=drift)
                wait_event0()
                # increment("B:VIMLUP")

            else:
                if abs(change) > max_change:
                    logger.info(
                        "Desired change %s is too large (>%s).", change, max_change
                    )
                    diag += 100  # TODO: I don't understand what this is doing, maybe don't use a magic number

                elif abs(change) < 0.001:
                    logger.info("Desired change %s is too small (<0.001).", change)
                    diag += 1000  # TODO: I don't understand what this is doing, maybe don't use a magic number
                    sleep(1)  # TODO: Why wait? And not above?

                else:
                    logger.info("Conditions have changed too much from initial.")
                    # If beam quality is not good, wait an extra supercycle.
                    wait_event0()
                    delay1 = 1  # this wait moved below so B:VIMDIAG will be set first

                # general_setter(parameter="B:VIMCHG", value=0)
                sleep(1)  # TODO: Why wait?
                # general_setter(parameter="B:VIMERR", value=error)
        else:
            logger.debug("B:VIMDBUG is set to debug mode on, so no VIMIN settings will be made.")
            # general_setter(parameter="B:VIMCHG", value=change)
            sleep(1)  # TODO: Why wait?
            # general_setter(parameter="B:VIMERR", value=error)

    



def main(variables):
    global a0
    global b0
    global c0
    global a1
    global b1
    global c1
    global limit
    global maxs06
    global max125
    global maxs13
    global maxs12
    global check_limit
    global limit_test
    global b_vimlup

    # DECLARATIONS
    pre_mode = 0
    b_scale = 0.062
    a_scale = 0.18
    c_scale = 3.24
    diag = 0
    delay1 = 0
    debug = 0
    prev_change = 0

    # Do not launch if control is off
    if launch() is False:
        logger.info("B:VIMLUP is off.")
    sleep(1)  # TODO: Why wait?

    # general_setter(parameter="B:VIMDIAG", value=0)

    # Zero out logging parameters. (Moved below to just before loop starts)
    # general_setter(parameter="B:VMLPMR.CONTROL", value="on")
    sleep(1)  # TODO: Why wait?
    # general_setter(parameter="B:VIMLUP", value=-9999)

    # Set lock for script to prevent more than 1 instance running at once.
    # l0ck = random.randint(1, 999999)
    # key = l0ck
    # k1 = general_getter(parameter="B:VIMLCK")

    # If new lock is same as old lock, abort launch and turn off tuner.
    # if k1 == l0ck:
    #     general_setter(parameter="B:VIMLUP.CONTROL", value="off")
    #     general_setter(parameter="B:VIMLUP", value=-3)
    #     logger.error("Key lock error")
    #     deltaset_vimdiag(1000000)

    # set B:VIMLCK l0ck
    # general_setter(parameter="B:VIMLCK", value=l0ck)

    # Check for max heartbeat limit mode or no limit mode.
    # If B:VIMLMT is set to 0, do not limit number of heartbeats.
    limit = 0 # general_getter(parameter="B:VIMLMT")
    limit_test = limit == 0

    logger.info("Initialize")

    # Check mode and default mode 1 to start script if not specified.
    mode = check_mode()
    diag = diag_from_mode(mode, diag)

    if mode == 0:
        # general_setter(parameter="B:VIMMOD", value=1)
        # general_setter(parameter="B:VMDMIR", value=1)
        mode = 1
        pre_mode = 1
    else:
        pre_mode = mode

    # Set tuning window and zeros initial parameters, grabs current loss ratio
    # if tuning mode is +1,2 or 3, get initial target ratio here
    vimin_min, vimin_max, limit_test, _, vimin, max_change, stepcut = initialize(variables).values()
    logger.debug("a0: %s", a0)
    wait_event0()
    wait_event0()
    # general_setter(parameter="B:VIMLUP", value=0)

    mode = check_mode()
    diag = diag_from_mode(mode, diag)
    pre_mode = mode

    # If tuning mode is -1,-2,or -3 get initial target ratio here
    # a0 = general_getter(parameter="B:VIMTGT1")
    # general_setter(parameter="B:VTGMR1", value=a0)
    # b0 = general_getter(parameter="B:VIMTGT2")
    # general_setter(parameter="B:VTGMR2", value=b0)
    # c0 = general_getter(parameter="B:VIMTGT3")
    # general_setter(parameter="B:VTGMR3", value=c0)

    logger.debug("a0: %s", a0)
    logger.info("Start main loop")

    logger.debug(("Loop is starting with the following parameters: "
                  "launch=%s, vimin_min=%s, vimin=%s, vimin_max=%s, limit_test=%s"),
                 launch(), vimin_min, vimin, vimin_max, limit_test)

    while (
        launch() is True and vimin <= vimin_max and vimin >= vimin_min and limit_test is True
    ):  # and key == l0ck
        """
        Tuning loop while tuner is on, setting is within tuning window,
        count is less than limit, and only 1 instance is running.
        """
        logger.debug("Inside the main loop")
        diag = 0

        # Check tuning mode and initialize if necessary
        mode = check_mode()
        diag = diag_from_mode(mode, diag)
        vimin_min, vimin_max, limit_test, mbtt, vimin, max_change, stepcut = initialize(variables).values()
        vistart = vimin

        if mode != pre_mode and mode != 0:
            logger.info("Mode change detected %s -> %s", pre_mode, mode)
            pre_mode = mode
        elif mode == 0:
            logger.info("Reinitialize mode %s", pre_mode)
            # TODO: `pre_variables` is not used.
            mode = pre_mode  # TODO: What does setting mode = mode do?
            # general_setter(parameter="B:VIMMOD", value=mode)

        # general_setter(parameter="B:VMDMIR", value=mode)

        # increment("B:VIMLUP")


        maxs06, maxs12, max125, maxs13= get_max().values()

        
        s06, s12, one25, s13 = get_current_values().values()


        norm125 = one25 / max125
        norms12 = s12 / maxs12
        norms13 = s13 / maxs13
        norms06 = s06 / maxs06

        diag, runtest = q_check2(
            event_ten=variables["event_ten"],
            event_fifty_three=variables["event_fifty_three"],
            diag=diag,
            norm125=norm125,
            norms12=norms12,
            norms13=norms13,
            norms06=norms06,
            mbtt=mbtt,
        ).values()

        # Current loss ratios

        b2 = s06 / one25
        a2 = s06 / s13
        c2 = s12 / one25

        # Calculate loss ratio error from target ratios

        a_error = a1 - a2
        b_error = b1 - b2
        c_error = c1 - c2
        a0_error = a0 - a2
        b0_error = b0 - b2
        c0_error = c0 - c2

        # TODO: Were checking the mode again!?
        if mode == 1:
            error = a_error
            scale = a_scale
        elif mode == 2:
            error = b_error
            scale = b_scale
        elif mode == 3:
            error = c_error
            scale = c_scale
        elif mode == -1:
            error = a0_error
            scale = a_scale
        elif mode == -2:
            error = b0_error
            scale = b_scale
        elif mode == -3:
            error = c0_error
            scale = c_scale
        else:
            error = 0
            scale = 0
            #general_setter(parameter="B:VIMLUP", value=-2.1)
            #general_setter(parameter="B:VIMLUP.CONTROL", value="off")

        # Calculate recommended setting change from error
        change = error * scale * stepcut
        sleep(1)  # TODO: Why wait?
        # TODO: I think there are better ways to handle formatting
        logger.info("Autotune Update:")
        logger.info(
            "Mode %s error: %s. Scale: %s, stepcut: %s", mode, error, scale, stepcut
        )
        logger.info("Recommended change: %s", change)

        # Check to make sure only 1 instance of this script is running
        # before making changes.
        # key = general_getter(parameter="B:VIMLCK")
        # if key != l0ck:
        #     deltaset_vimdiag(1000000)
        #     logger.warn("Multiple scripts running, exiting.")

        # Check to make sure B:VIMLUP is still on before making changes
        # if launch() == False:
        #     general_setter(parameter="B:VIMLUP.SETTING", value=-1)

        change = reduce_change_if_same(change, prev_change)

        # Unfortunatly, even though we can clamp in a single command below, we need to check
        # the magnitude of the change to set the diag value.
        if abs(change) > max_change:
            diag += 100

        change = vimax_clamp(change, max_change)

        # if the previous tuning cycle was a missing beam
        # /high loss cycle then reduce the next recomended change by half
        if delay1 == 1:
            change = 0.5 * change

        delay1 = 0

        make_autotune_update(change, max_change, runtest, prev_change, diag, delay1)

        
        # general_setter(parameter="B:VIMDIAG", value=diag)
        wait_event0()

        # If missing beam events or high losses were detected,
        # wait 2 additional supercycles
        if delay1 == 1:
            wait_event0()
            wait_event0()

            # Update heartbeat limit

        limit = general_getter(parameter="B:VIMLMT")

        # If B:VIMLMT is not set to 0, check for heartbeats within limit

        if limit !=0:
            check_limit = True
        elif limit ==0:
            check_limit = False

        if check_limit is True: #If B:VIMLMT is not set to 0, check for heartbeats within limit
            if b_vimlup  >= limit :
                limit_test = False
                diag += 10_000_000  # TODO: What is this!? 🤣 Don't use magic numbers

        # Check for other instances of script
        # key = general_getter(parameter="B:VIMLCK")

    # if the while loop ended due to key!=l0ck (mult scripts running), exit script

    # if key != l0ck:
    #     deltaset_vimdiag(1000000)

    #     ### if B:VIMLUP was turned off manually:

    # elif launch() == False:
    #     general_setter(parameter="B:VIMLUP", value=-1)
    #     general_setter(parameter="B:VMLPMR.CONTROL", value="off")

    # ### if loop exited due to out of window or heartbeat limit:

    # elif launch() == True:
    #     general_setter(parameter="B:VIMLUP.CONTROL", value="off")
    #     general_setter(parameter="B:VIMLUP", value=4)
    #     general_setter(parameter="B:VMLPMR.CONTROL", value="off")

    # TODO: This logic is equivalent to vimin != vimin_max. Is that what we want?
    # TODO: Confirm logic and choose a solution.
    # if vimin_min > vimin > vimin_max:
    #     diag += 1000
    # if vimin > vimin_max or vimin < vimin_min:
    #     diag += 1000

    # general_setter(parameter="B:VIMDIAG", value=diag)
    # general_setter(parameter="B:VMLPMR.CONTROL", value="off")


if __name__ == "__main__":
    mode = input("Enter 1 - Mock Test, 2 - Live Test ")

    # We only check if it should be live
    # We default to mock
    if mode == "2":
        variables = {
            "bls060": "B:BLS060",
            "bls120": "B:BLS120",
            "bl1250": "B:BL1250",
            "bls130": "B:BLS130",
            "event_fifty_three": "G:E53SCT",
            "event_ten": "G:E10SCT",
            "vimin": "B:VIMIN",
        }
    else:
        variables = {
            "bls060": "B:DATS06",
            "bls120": "B:DATS12",
            "bl1250": "B:DAT125",
            "bls130": "B:DATS13",
            "event_fifty_three": "B:DATE53",
            "event_ten": "B:DATE10",
            "vimin": "B:DATPY",
        }

    logger.debug(variables)

    main(variables)
    # TODO: You mentioned error handling, we should add that.
