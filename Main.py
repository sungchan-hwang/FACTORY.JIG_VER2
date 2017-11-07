
########################################################
# import
import traceback, time, json, datetime, queue, requests, os, sys, copy, serial, socket, base64
from subprocess import PIPE, Popen
from _thread import start_new_thread
from operator import itemgetter
from flask import Flask, request, g
import RPi.GPIO as gpio

import Log as log
import Common as common
#import Socket as socket

########################################################
# define

# delay
DELAY_GLOBAL = 0.1
DELAY_GPIO_INPUT = 0.1
DELAY_CTRL_LED = 0.5
DELAY_RESET_TAG = 0.05
DELAY_CTRL_FU = 2
DELAY_CTRL_CYLINDER = 2
DELAY_CHK_FU = 1

# gpio output pin
GOPS_TEST_OK = 19
GOPS_TEST_NG = 21
GOPS_ETH_OK = 12
GOPS_ETH_NG = 16
GOPS_DN_OK = 18
GOPS_DN_NG = 22
GOPS_RF_OK = 24
GOPS_RF_NG = 26
GOPS_NFC_OK = 32
GOPS_NFC_NG = 36
GOPS_MAC_OK = 38
GOPS_MAC_NG = 40

GOPS_RESET = 7                # tag reset control
GOPS_FU = 33                # fu control
GOPS_CYLINDER = 35          # cylinder control
GOPS_SWITCHED_PWR = 37      # power on tag

# gpio input pin
GIPS_FU = 11
GIPS_CYLINDER = 13
GIPS_TAG = 15
GIPS_BTN_RESET = 29
GIPS_BTN_START = 31

# control & status
CTRL_ON = 1
CTRL_OFF = 0
CTRL_UP = 0
CTRL_DOWN = 1
CTRL_LED_ON = 0
CTRL_LED_OFF = 1
STATUS_ON = 0
STATUS_OFF = 1
STATUS_CYLINDER_DOWN = 1
STATUS_CYLINDER_UP = 0
POWER_ON = 1
POWER_OFF = 0

# path
PATH_SCRIPT = "/home/MP/config/"
PATH_TAG_IMAGE = "/home/MP/data/"
PATH_JLINK = "/home/MP/jlink/"


########################################################
# global
# log
g_logger = log.CLog(log.LEV_CURRENT, common.LOG_PATH + common.LOG_FILE_NAME)
g_logger.create_logger(__name__)

# web
flaskapp = Flask(__name__)

# env
g_env = {}

# script
g_script = {}

# event
g_event = {}

# process
g_process = None

# frequency
g_freq_list = {}
for i in range(16):
    g_freq_list[11 + i] = 2405 + (5 * i)

# web tx
g_web_tx_index = 1

# test status
g_test_status = "READY"

# loop
g_loop = {"thread_input_gpio": True, "thread_manual_test": False}

# input pin status
g_input_pin = {"g_chk_start": 1, "g_chk_reset": 1, "g_chk_tag": 1, "g_chk_fu": 1, "g_chk_cylinder": 0}

########################################################
# function


'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
    Decorator
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''


def add_object_info():
    def function(func_name):
        def argument(*args, **kwargs):
            #g_logger.debug("{} > args :: {}, kwargs :: {}".format(func_name.__name__, args, kwargs))
            return func_name(*args, **kwargs)
        return argument
    return function


'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
    Exception
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''


class CMpError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
    Gpio
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''


@add_object_info()
def fn_init_gpio():
    #leds = [GOPS_TEST_OK, GOPS_TEST_NG, GOPS_ETH_OK, GOPS_ETH_NG, GOPS_DN_OK, GOPS_DN_NG, GOPS_RF_OK, GOPS_RF_NG,
    leds = [GOPS_ETH_OK, GOPS_ETH_NG, GOPS_DN_OK, GOPS_DN_NG, GOPS_RF_OK, GOPS_RF_NG,
            GOPS_NFC_OK, GOPS_NFC_NG, GOPS_MAC_OK, GOPS_MAC_NG]

    #ctrls = [GOPS_FU, GOPS_CYLINDER, GOPS_SWITCHED_PWR, GOPS_RESET]
    ctrls = [GOPS_FU, GOPS_CYLINDER, GOPS_SWITCHED_PWR]

    gpio.setmode(gpio.BOARD)

    # output gpio
    for led in leds:
        gpio.setup(led, gpio.OUT)

    for ctrl in ctrls:
        gpio.setup(ctrl, gpio.OUT)

    # input_gpio
    start_new_thread(thread_input_gpio, (None,))
    start_new_thread(thread_proc_button, (None,))


@add_object_info()
def thread_input_gpio(arg=None):
    global g_input_pin

    g_logger.debug("thread_input_gpio > start")

    statuses = {"g_chk_fu": GIPS_FU, "g_chk_cylinder": GIPS_CYLINDER, "g_chk_tag": GIPS_TAG,
                "g_chk_reset": GIPS_BTN_RESET, "g_chk_start": GIPS_BTN_START}

    # set input pin
    for key in statuses:
        gpio.setup(statuses[key], gpio.IN)

    while g_loop["thread_input_gpio"]:
        display_flag = False
        for key in statuses:
            if g_input_pin[key] != gpio.input(statuses[key]):
                g_input_pin[key] ^= 0x01
                display_flag = True

                if ("g_chk_reset" == key) and (STATUS_ON == g_input_pin[key]):
                    fn_event_fire("button", "g_chk_reset")

                if ("g_chk_start" == key) and (STATUS_ON == g_input_pin[key]):
                    """
                    if "test" == g_env["mode"]:
                        fn_event_fire("test", {"name": "test_ready", "data": {}})
                    else:
                        fn_event_fire("button", "g_chk_start")
                    """
                    fn_event_fire("button", "g_chk_start")
                    
        if display_flag:
            g_logger.debug("thread_input_gpio > g_chk_fu :: {}, g_chk_cylinder :: {}, g_chk_tag :: {}, g_chk_reset :: {}, g_chk_start :: {}".
                  format(g_input_pin["g_chk_fu"], g_input_pin["g_chk_cylinder"], g_input_pin["g_chk_tag"],
                         g_input_pin["g_chk_reset"], g_input_pin["g_chk_start"]))

        time.sleep(DELAY_GPIO_INPUT)

    g_logger.debug("thread_input_gpio > end")


@add_object_info()
def thread_proc_button(arg=None):
    global g_test_status

    g_logger.debug("thread_proc_button > start")

    while g_loop["thread_input_gpio"]:
        btn = fn_event_wait("button")

        if "g_chk_reset" == btn:
            #gpio.output(GOPS_RESET, CTRL_ON)
            gpio.output(GOPS_SWITCHED_PWR, POWER_OFF)
            gpio.output(GOPS_CYLINDER, CTRL_UP)
            time.sleep(DELAY_CTRL_CYLINDER)
            gpio.output(GOPS_FU, CTRL_UP)
            g_test_status = "READY"
        elif "g_chk_start" == btn:
            gpio.output(GOPS_FU, CTRL_DOWN)
            time.sleep(DELAY_CTRL_FU)
            gpio.output(GOPS_CYLINDER, CTRL_DOWN)
            time.sleep(DELAY_CTRL_CYLINDER)
            g_test_status = "TESTING"
            
        time.sleep(1)

    g_logger.debug("thread_proc_button > end")



@add_object_info()
def fn_clear_led(leds):
    g_logger.debug("fn_clear_led > LED :: ALL OFF.")
    for led in leds:
        gpio.output(led, CTRL_LED_OFF)


'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
    Event
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''


def fn_check_event(tag=None):
    def function(func_name):
        def argument(*args, **kwargs):
            if (("create" == tag) and (args[0] not in g_event)) or ((None == tag) and (args[0] in g_event)):
                return func_name(*args, **kwargs)
            else:
                t = "was already" if "create" == tag else "didn't"
                g_logger.warn("fn_check_event > '{}' event {} created.".format(args[0], t))
                return None
        return argument
    return function


@fn_check_event("create")
def fn_event_create(name):
    global g_event

    g_event[name] = {'enable': True, 'event': []}
    g_logger.debug("fn_event_create > name :: {}".format(name))
    return True

"""
@fn_check_event()
def fn_event_ctrl(name, ctrl):
    global g_event

    g_event[name]['enable'] = ctrl
    return True
"""

@fn_check_event()
def fn_event_fire(name, e_data):
    if g_event[name]['enable']:
        g_event[name]['event'].append(e_data)
        return True

    return False


@fn_check_event()
def fn_event_wait(name, e_timeout=None):
    """
    fn_event_ctrl(name, True)
    e_data = g_event[name]['event'].get(timeout=e_timeout)
    fn_event_ctrl(name, False)
    fn_event_flush(name)
    """
    e_data = None
    if 0 < len(g_event[name]['event']):
        e_data = g_event[name]['event'].pop(0)  
        
    return e_data

"""
@fn_check_event()
def fn_event_flush(name):
    try:
        while True:
            g_event[name]['event'].get_nowait()
    except queue.Empty:
        pass

    return True
"""

'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
    Web
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''


def thread_web_run(ip=None, port=None):
    if (None == ip) and (None == port):
        g_logger.error("thread_web_run > Wep ip : None, port : None")
        return False

    flaskapp.run(host=ip, port=port)
    return True


@flaskapp.route("/manual_test/", methods=['POST'])
def fn_web_rx_manual_test():
    global g_process
    global g_input_pin

    req_data = json.loads(request.data.decode())
    fn_event_fire("test", req_data)

    return "OK"
	
	
@flaskapp.route("/select_tag/", methods=['POST'])
def fn_web_rx_select_tag():
    req_data = json.loads(request.data.decode())
	
    tag_inch = req_data['tag']
    if "R154" == tag_inch:
        os.system("cp " + PATH_SCRIPT + "script_1p54.json " + PATH_SCRIPT + "script.json")
    elif "R213" == tag_inch:
        os.system("cp " + PATH_SCRIPT + "script_2p13.json " + PATH_SCRIPT + "script.json")
    elif "R290" == tag_inch:
        os.system("cp " + PATH_SCRIPT + "script_2p90.json " + PATH_SCRIPT + "script.json")
    elif "R290F" == tag_inch:
        os.system("cp " + PATH_SCRIPT + "script_2p90_freeze.json " + PATH_SCRIPT + "script.json")
    elif "R420" == tag_inch:
        os.system("cp " + PATH_SCRIPT + "script_4p20.json " + PATH_SCRIPT + "script.json")
    elif "R750" == tag_inch:
        os.system("cp " + PATH_SCRIPT + "script_7p50.json " + PATH_SCRIPT + "script.json")    
    else:
        return json.dumps({"msg": "result_select_tag", "data": "NG(tag inch)"})
	
    return json.dumps({"msg": "result_select_tag", "data": "OK"})
	
	
@flaskapp.route("/upload/", methods=['POST'])
def fn_web_rx_upload():
    req_data = json.loads(request.data.decode())
	
    try:
        for f_name in req_data["script"]:
            decoded_binary = base64.urlsafe_b64decode(req_data["script"][f_name])
            with open(PATH_SCRIPT + f_name, 'wb') as f:
                f.write(decoded_binary)

        for f_name in req_data["image"]:
            decoded_binary = base64.urlsafe_b64decode(req_data["image"][f_name])
            with open(PATH_TAG_IMAGE + f_name, 'wb') as f:
                f.write(decoded_binary)
    except Exception:
        tb = traceback.format_exc()
        msg = "\r\n{:*^57}\r\n{}\r\n{}".format("[Error-MP]", tb, "-" * 57)
        g_logger.exception(msg)

        return json.dumps({"msg": "result_upload", "data": "NG(Upload)"})
		
    return json.dumps({"msg": "result_upload", "data": "OK"})
	

@add_object_info()
def fn_web_request_msg(ip, method, url_path, data=None):
    ret_value = None
    exception_type = None

    try:
        mp_server = "http://{}{}".format(ip, url_path)
        header = {"Content-Type": "application/json", "Access-Token": "28c59b9503abe26efd105350bb59fc921ef702d7"}
        if "POST" == method:
            resp = requests.post(mp_server, json=data, timeout=30, headers=header)
        else:
            resp = requests.get(mp_server, timeout=30, headers=header)

        if 200 == resp.status_code:
            if "" != resp.text:
                resp_data = json.loads(resp.text)
                if "POST" == method:
                    ret_value = resp_data
                else:
                    g_logger.debug("resp :: ok")
                    ret_value = resp_data
        else:
            exception_type = "tx_error"
            g_logger.warn("response status code :: {}".format(resp.status_code))
    except requests.exceptions.ConnectionError as e:
        exception_type = "ethernet_error"
        g_logger.error("[Error] {}-{}:{} :: The jig can't connect to server".format(sys._getframe().f_code.co_name, method, url_path))
        os.system("ifdown eth0 && ifup eth0")
    except Exception as e:
        tb = traceback.format_exc()
        msg = "{:*^57}\r\n{}\r\n{}".format("[Error-Gateway]", tb, "-" * 57)
        g_logger.error(msg)

    return ret_value, exception_type


@add_object_info()
def fn_web_tx_get_tag_mac():
    global g_web_tx_index

    net_addr = "{}:{}".format(g_env["mp_server"]["ip"], g_env["mp_server"]["port"])
    for i in range(2):
        resp_data, exception_type = fn_web_request_msg(net_addr, "POST", "/api/v1/amac/assign?{}".format(g_web_tx_index), data="")
        g_web_tx_index += 1

        if None != resp_data:
            return True, resp_data
        elif "tx_error" == exception_type:
            return False, None
        elif "ethernet_error" == exception_type:
            continue

    return None, None


@add_object_info()
def fn_web_tx_result():
    global g_web_tx_index

    result_data = {}

    result_data["batchNumber"] = g_script["header"]["batchNumber"]
    result_data["pcNumber"] = g_env["pcNumber"]
    result_data["tagType"] = g_script["header"]["tag_type"]
    result_data["tagMac"] = g_process["result"]["tagMac"]
    result_data["result"] = g_process["result"]["result"]
    result_data["startTime"] = g_process["start_time"].strftime('%Y-%m-%d %H:%M:%S')
    result_data["endTime"] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    result_data["details"] = g_process["result"]["detail"]
    print("~~!!!~~~ fn_web_tx_result :: {}".format(result_data))

    net_addr = "{}:{}".format(g_env["mp_server"]["ip"], g_env["mp_server"]["port"])
    for i in range(2):
        resp_data, exception_type = fn_web_request_msg(net_addr, "POST", "/api/v1/production/result?{}".format(g_web_tx_index), data=result_data)
        g_web_tx_index += 1

        if None != resp_data:
            return True, resp_data
        elif "tx_error" == exception_type:
            return False, None
        elif "ethernet_error" == exception_type:
            continue

    return None, None


'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
    Serial
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''


@add_object_info()
def fn_serial_send_data(tx_data, timeout, check_success_flag):
    result = False
    ser = None
    rx_data = ""
    working_time = 0
    rest_time = 0

    try:
        # serial open
        ser = serial.Serial('/dev/ttyS0', 9600)

        # wait for receiving "test req" message.
        result, rx_data, working_time = fn_serial_wait_data(ser, ["test req"], timeout)
        if False == result:
            raise CMpError("fn_serial_send_data > Not received 'test req' data")

        # send data
        g_logger.debug("tx data :: {}, [{}]".format(tx_data, [("%02X" % i) for i in tx_data]))
        ser.write(tx_data)

        # check success
        if check_success_flag:
            rest_time = timeout - working_time
            result, rx_data, working_time = fn_serial_wait_data(ser, ["succ", "fail", "evm", "type"], rest_time)
            if (False == result) or ("succ" != rx_data):
                result = False
                raise CMpError("fn_serial_send_data > Not received 'succ' data")
        else:
            result = True
    except CMpError as e:
        g_logger.error(e)
    except Exception:
        tb = traceback.format_exc()
        msg = "\r\n{:*^57}\r\n{}\r\n{}".format("[Error-Serial]", tb, "-" * 57)
        g_logger.exception(msg)
    finally:
        # serial close
        if ser != None:
            ser.close()

    return result, rx_data, (rest_time - working_time)


@add_object_info()
def fn_serial_wait_data(ser, wait_data, timeout):
    result, loop = False, True
    recv_data, r_data = "", ""

    st = time.time()

    try:
        while loop:
            if time.time() - st < timeout:
                if ser.inWaiting() > 0:
                    for rx_data in ser.read():
                        recv_data += chr(rx_data)

                    for wd in wait_data:
                        if wd in recv_data:
                            g_logger.debug("wait_data :: {}, recv_data :: {}".format(wd, recv_data))
                            r_data, loop = wd, False
                            break
            else:
                raise CMpError("fn_serial_wait_data > TIMEOUT :: waiting for {} data :: timeout".format(wait_data))
        result = True
    except CMpError as e:
        g_logger.error(e)
    except Exception:
        tb = traceback.format_exc()
        msg = "\r\n{:*^57}\r\n{}\r\n{}".format("[Error-Serial]", tb, "-" * 57)
        g_logger.exception(msg)

    return result, r_data, (time.time() - st)


'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
    TCP/IP
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''


@add_object_info()
def fn_ni_measure_rf(svr_ip, svr_port, freq, tag_power, loss, timeout):
    sock = None
    wait_data = ""
    power, offset_evm, freq_error = "-99.999", "99.999", "99999.999"

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(True)
        sock.connect((svr_ip, svr_port))
        # check connection
        sock.sendall(b"*IDN?\n")
        rx_data = sock.recv(1024)
        g_logger.debug("fn_ni_measure_rf > ni information :: {}".format(rx_data))

        # reset
        sock.sendall(b"*RST\n")

        # send config
        sock.sendall(b"SYSTem:RFSA:ZIGBee:PRESet\n")
        sock.sendall("CONFigure:RFSA:ZIGBee:FREQuency {}.00E6\n".format(int(freq)).encode())
        sock.sendall(b"CONFigure:RFSA:ZIGBee:IQRate 25E6\n")
        sock.sendall(b"CONFigure:RFSA:ZIGBee:BLENgth 0.01\n")
        sock.sendall("CONFigure:RFSA:ZIGBee:POWer {}.0\n".format(tag_power - loss + 3).encode())
        sock.sendall("TRIGger:RFSA:ZIGBee:THREshold {}.0\n".format(tag_power - loss - 20).encode())
        sock.sendall(b"TRIGger:RFSA:ZIGBee:SOUrce PowerEdge\n")
        sock.sendall(b"TRIGger:RFSA:ZIGBee:SOUrce?\n")
        rx_data = sock.recv(1024)
        g_logger.debug("fn_ni_measure_rf > power edge :: {}".format(rx_data))

        sock.sendall(b"TRIGger:RFSA:ZIGBee:DELay 0\n")
        sock.sendall(b"TRIGger:RFSA:ZIGBee:TOUT 2000\n")
        sock.sendall(b"TRIGger:RFSA:ZIGBee:MQTime 0\n")
        sock.sendall(b"CONFigure:RFSA:ZIGBee:MEASurement:AVERaging 1\n")
        sock.sendall(b"CONFigure:RFSA:ZIGBee:MEASurement:RBW 100E3\n")

        sock.sendall(b"INITiate:RFSA:ZIGBee\n")
        sock.sendall(b"*OPC?\n")
        rx_data = sock.recv(1024)
        g_logger.debug("fn_ni_measure_rf > config status :: {}".format(rx_data))

        # check to complete measure
        while True:
            sock.sendall(b"FETCh:RFSA:ZIGBee:STATe?\n")
            rx_data = sock.recv(1024)
            if b"READY" in rx_data:
                break
        g_logger.debug("fn_ni_measure_rf > measure status :: Ready")

        # result power
        sock.sendall(b"FETCh:RFSA:ZIGBee:MEASurement:TXPower:RESults?\n")
        rx_data = sock.recv(1024)
        if b"NaN" in rx_data:
            raise CMpError("fn_serial_wait_data > Received power :: {}".format(rx_data))
        else:
            power = rx_data.decode()
            if '.' not in power:
                power = power[:-1] + ".0000"				
            g_logger.debug("fn_ni_measure_rf > result power :: {}".format(power))

        # result offset evm
        sock.sendall(b"FETCh:RFSA:ZIGBee:MEASurement:OEVM:RESults?\n")
        rx_data = sock.recv(1024)
        if b"NaN" in rx_data:
            raise CMpError("fn_serial_wait_data > Received offset_evm :: {}".format(rx_data))
        else:
            offset_evm = rx_data.decode()
            if '.' not in offset_evm:
                offset_evm = offset_evm[:-1] + ".0000"			
            g_logger.debug("fn_ni_measure_rf > result offset evm :: {}".format(offset_evm))

        # result freq error
        sock.sendall(b"FETCh:RFSA:ZIGBee:MEASurement:FOFFset:RESults?\n")
        rx_data = sock.recv(1024)
        if b"NaN" in rx_data:
            raise CMpError("fn_serial_wait_data > Received freq_error :: {}".format(rx_data))
        else:
            freq_error = rx_data.decode()
            if '.' not in freq_error:
                freq_error = freq_error[:-1] + ".0000"
            g_logger.debug("fn_ni_measure_rf > result freq error :: {}".format(freq_error))
    except CMpError as e:
        g_logger.error(e)
    finally:
        # socket close
        if sock != None:
            sock.close()

    idx_p = power.index('.')
    idx_e = offset_evm.index('.')
    idx_f = freq_error.index('.')
    return power[:idx_p+3], offset_evm[:idx_e+3], freq_error[:idx_f+3]


'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
    Test Application
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''


def fn_test_proc():
    def function(func_name):
        def argument(*args, **kwargs):
            proc_list = func_name(*args, **kwargs)

            for target, ctrl, delay, msg in proc_list:
                g_logger.debug("{} > {}".format(func_name, msg))
                gpio.output(target, ctrl)
                time.sleep(delay)
            return True
        return argument
    return function


@add_object_info()
def fn_test_button(data):
    global g_input_pin
    global g_test_status

    g_input_pin["g_chk_start"] = data["g_chk_start"]
    g_input_pin["g_chk_reset"] = data["g_chk_reset"]

    if 0 == data["g_chk_reset"]:
        #gpio.output(GOPS_RESET, CTRL_ON)
        gpio.output(GOPS_SWITCHED_PWR, POWER_OFF)
        gpio.output(GOPS_CYLINDER, CTRL_UP)
        time.sleep(DELAY_CTRL_CYLINDER)
        gpio.output(GOPS_FU, CTRL_UP)
        g_test_status = "READY"
    elif 0 == data["g_chk_start"]:
        gpio.output(GOPS_FU, CTRL_DOWN)
        time.sleep(DELAY_CTRL_FU)
        gpio.output(GOPS_SWITCHED_PWR, POWER_ON)
        gpio.output(GOPS_CYLINDER, CTRL_DOWN)
        time.sleep(DELAY_CTRL_CYLINDER)
        g_test_status = "TESTING"


@fn_test_proc()
def fn_test_gpio(data):
    return data

'''
@fn_test_proc()
def fn_test_status_sens(data):
    proc_list = [
        [GOPS_FU, CTRL_DOWN, DELAY_CTRL_FU, "FU :: DOWN"],
        [GOPS_CYLINDER, CTRL_DOWN, DELAY_CTRL_CYLINDER, "CYLINDER :: DOWN"],
        [GOPS_SWITCHED_PWR, POWER_ON, DELAY_RESET_TAG, "TAG POWER :: ON"],
        """
        [GOPS_RESET, CTRL_ON, DELAY_RESET_TAG, "TAG RESET :: ON"],
        [GOPS_RESET, CTRL_OFF, DELAY_RESET_TAG, "TAG RESET :: OFF"],
        [GOPS_RESET, CTRL_ON, DELAY_RESET_TAG, "TAG RESET :: ON"],
        #"""
        [GOPS_SWITCHED_PWR, POWER_OFF, DELAY_RESET_TAG, "TAG POWER :: OFF"],
        [GOPS_CYLINDER, CTRL_UP, DELAY_CTRL_CYLINDER, "CYLINDER :: UP"],
        [GOPS_FU, CTRL_UP, DELAY_CTRL_FU, "FU :: UP"]
    ]

    return proc_list


@add_object_info()
def fn_test_ready(data):
    global g_test_status

    g_logger.debug("fn_test_ready > {}".format("FU :: DOWN"))
    gpio.output(GOPS_FU, CTRL_DOWN)
    time.sleep(DELAY_CTRL_FU)

    g_logger.debug("fn_test_ready > {}".format("CYLINDER :: DOWN"))
    gpio.output(GOPS_CYLINDER, CTRL_DOWN)
    time.sleep(DELAY_CTRL_CYLINDER)

    cfu = True if 0 == g_input_pin["g_chk_fu"] else False

    if cfu:
        g_logger.debug("fn_test_ready > {}".format("TAG POWER :: ON"))
        gpio.output(GOPS_SWITCHED_PWR, POWER_ON)
        time.sleep(DELAY_RESET_TAG)

        g_test_status = "TESTING"
    else:
        g_logger.debug("fn_test_ready > TIMEOUT :: FU pin")

        g_logger.debug("fn_test_ready > {}".format("CYLINDER :: UP"))
        gpio.output(GOPS_CYLINDER, CTRL_UP)
        time.sleep(DELAY_CTRL_CYLINDER)

        g_logger.debug("fn_test_ready > {}".format("FU :: UP"))
        gpio.output(GOPS_FU, CTRL_UP)
        time.sleep(DELAY_CTRL_FU)



@add_object_info()
def fn_test_download(data):
    result = os.system("./swdp {}{} 0 1".format(common.TAG_IMG_PATH, data["file"]))
    g_logger.debug("fn_test_download > Result :: {}".format("OK" if (0 == result) else "NG"))


@add_object_info()
def fn_test_get_mac(data):
    result, resp_data = fn_web_tx_get_tag_mac()
    g_logger.debug("fn_test_get_mac > result :: {}, resp_data :: {}".format(result, resp_data))


@add_object_info()
def fn_test_write_mac(data):
    g_logger.debug("fn_test_write_mac > {}".format("TAG POWER :: ON -> OFF -> ON"))
    fn_tag_reset()

    reverse_data = bytearray.fromhex(data["tagMac"][:6] + "FFFE" + data["tagMac"][6:])
    reverse_data.reverse()
    cs = sum(reverse_data) + sum(bytearray(data['abstractMac'].encode('ascii'))) + sum(bytearray(data['tag_type'].encode('ascii')))

    tx_data = bytearray(b'macmacf') + reverse_data + bytearray(data['abstractMac'].encode('ascii') + data["tag_type"].encode('ascii'))
    tx_data += bytearray.fromhex("%02x" % ((cs >> 8) & 0xFF) + ("%02x" % (cs & 0xFF)) + data["tag_type"])
    result, rx_data, rest_time = fn_serial_send_data(tx_data, 10, True)
    g_logger.debug("fn_test_write_mac > result :: {}, rx_data :: {}, rest_time :: {}, tx_data :: {}".format(result, rx_data, rest_time, tx_data))


@add_object_info()
def fn_test_nfc(data):
    g_logger.debug("fn_test_nfc > {}".format("TAG POWER :: ON -> OFF -> ON"))
    fn_tag_reset()

    g_logger.debug("fn_test_nfc > NFC :: WRITE")
    nfc_data = data["nfc_data"]
    tx_data = bytearray(b'nfc') + bytearray.fromhex("%02x00" % (len(nfc_data) + 1)) + bytearray(nfc_data.encode('ascii'))
    w_result, rx_data, rest_time = fn_serial_send_data(tx_data, 10, True)
    g_logger.debug("fn_test_nfc > result :: {}, rx_data :: {}, rest_time :: {}, tx_data :: {}".format(w_result, rx_data, rest_time, tx_data))


@add_object_info()
def fn_test_rf(data):
    for ch in data["ch"]:
        g_logger.debug("fn_test_rf > {}".format("TAG POWER :: ON -> OFF -> ON"))
        fn_tag_reset()

        g_logger.debug("fn_test_rf > RF :: {}ch".format(ch))
        tx_data = bytearray(b'evm') + bytearray.fromhex(("%02x" % ch) + ("%02x" % (ch ^ 0xFF)))
        w_result, rx_data, rest_time = fn_serial_send_data(tx_data, 10, False)
        g_logger.debug("fn_test_rf > result :: {}, rx_data :: {}, rest_time :: {}, tx_data :: {}".format(w_result, rx_data, rest_time, tx_data))

        power, offset_evm, freq_error = fn_ni_measure_rf(g_env["ni"]["ip"], g_env["ni"]["port"], g_freq_list[ch], data["tag_power"], data["loss"], 10)
        g_logger.debug("fn_test_rf > power :: {}, offset_evm :: {}, freq_error :: {}".format(power, offset_evm, freq_error))

        if data["threshold_power"] > float(power):
            g_logger.debug("fn_rf > {} :: Out of threshold range(Power) :: {}.".format(ch, power))

        if data["threshold_evm"] < float(offset_evm):
            g_logger.debug("fn_rf > {} :: Out of threshold range(Evm) :: {}.".format(ch, offset_evm))

        if (data["threshold_min_freq_err"] > float(freq_error)) or (data["threshold_max_freq_err"] < float(freq_error)):
            g_logger.debug("fn_rf > {} :: Out of threshold range(Freq Err) :: {}.".format(ch, freq_error))


@fn_test_proc()
def fn_test_finish(data):
    global g_test_status

    proc_list = [
        #[GOPS_RESET, POWER_OFF, DELAY_RESET_TAG, "TAG RESET :: OFF"],
        [GOPS_SWITCHED_PWR, POWER_OFF, DELAY_RESET_TAG, "TAG POWER :: OFF"],
        [GOPS_CYLINDER, CTRL_UP, DELAY_CTRL_CYLINDER, "CYLINDER :: UP"],
        [GOPS_FU, CTRL_UP, DELAY_CTRL_FU, "FU :: UP"]
    ]

    g_test_status = "READY"

    return proc_list
'''


@add_object_info()
def fn_function_test(function, arg):
    """
    proc_list = {
        "gpio": fn_test_gpio,
        "button": fn_test_button,
        "status_sens": fn_test_status_sens,
        "test_ready": fn_test_ready,
        "download": fn_test_download,
        "get_mac": fn_test_get_mac,
        "write_mac": fn_test_write_mac,
        "test_nfc": fn_test_nfc,
        "test_rf": fn_test_rf,
        "test_finish": fn_test_finish
    }
    """
    proc_list = {
        "gpio": fn_test_gpio,
        "button": fn_test_button
    }

    if function in proc_list:
        proc_list[function](arg)
    else:
        g_logger.warn("fn_function_test > Unknown function :: {}".format(function))

        
@add_object_info()
def thread_manual_test(arg=None):
    g_logger.debug("thread_manual_test > start")

    while g_loop["thread_manual_test"]:
        proc = fn_event_wait("test")

        if proc["name"] != None:
            proc_name = proc["name"]
            proc_data = proc["data"]

            fn_function_test(proc_name, proc_data)
            
        time.sleep(1)

    g_logger.debug("thread_manual_test > end")


'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
    Main Application
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''


@add_object_info()
def fn_load_file(name):
    with open(common.PROJECT_PATH + name) as file:
        read_data = file.read()

    return json.loads(read_data)


@add_object_info()
def fn_display_info(name, info):
    g_logger.info("\r\n{:*^57}".format(name))
    for item in info:
        if type(info) is dict:
            g_logger.info("%20s\t%s" % (item, info[item]))
        elif type(info) is list:
            g_logger.info("%20s\t%s" % ("", item))


@add_object_info()
def fn_program_start():
    global g_env

    g_logger.info("fn_program_start > Start program")

    # load config
    g_env = fn_load_file(common.CONFIG_FILE)
    fn_display_info(" Env ", g_env)

    # event
    g_logger.info("fn_start_program > Event :: Create.")
    fn_event_create("test")
    fn_event_create("button")

    # gpio
    g_logger.info("fn_program_start > GPIO :: Initialize.")
    fn_init_gpio()
    #leds = [GOPS_TEST_OK, GOPS_TEST_NG, GOPS_ETH_OK, GOPS_ETH_NG, GOPS_DN_OK, GOPS_DN_NG, GOPS_RF_OK, GOPS_RF_NG,
    leds = [GOPS_ETH_OK, GOPS_ETH_NG, GOPS_DN_OK, GOPS_DN_NG, GOPS_RF_OK, GOPS_RF_NG,
            GOPS_NFC_OK, GOPS_NFC_NG, GOPS_MAC_OK, GOPS_MAC_NG]
    fn_clear_led(leds)
    fn_jig_hw_init()

    # process
    g_logger.info("fn_program_start > Process information :: Reset.")
    fn_process_reset()
    fn_process_change_mode(g_env["mode"])

    """
    # manual test
    start_new_thread(thread_manual_test, (None,))
    """
    
    # wep server
    g_logger.info("fn_program_start > Wep server :: Start.")
    start_new_thread(thread_web_run, (g_env["jig"]["ip"], g_env["jig"]["port"],))

    return True


@add_object_info()
def fn_program_end():
    global g_loop

    g_logger.info("fn_program_end > End program")

    gpio.cleanup()
    g_loop["thread_input_gpio"] = False
    g_loop["thread_manual_test"] = False
    return True


@add_object_info()
def fn_process_change_mode(mode):
    global g_process

    g_process["mode"] = mode


@add_object_info()
def fn_process_reset():
    global g_process

    default_result = {}

    default_result["tagMac"] = ""
    default_result["result"] = "NG"
    default_result["start_time"] = None
    default_result["detail"] = {
        "download": "NT",
        "reset1": "NT",
        "rfTest": {"result": "NT", "data": None},
        "reset2": "NT",
        "nfc": "NT",
        "writeMac": "NT"}
    default_result["detail"]["rfTest"]["data"] = [
        {"ch": "11", "txPower": 0, "freqErr": 0, "evm": 0},
        {"ch": "18", "txPower": 0, "freqErr": 0, "evm": 0},
        {"ch": "26", "txPower": 0, "freqErr": 0, "evm": 0}
    ]

    current_proc = {"seq": 1, "enable": "yes", "name": "test start", "data": {}, "timeout": None, "retry": 1}
    g_process = {"mode": "normal", "current_proc": current_proc, "standby_proc_list": None, "start_time": 0,
                 "err_msg": "", "result": default_result}


@add_object_info()
def fn_process_load():
    global g_process
    global g_script

    # load script
    g_script = fn_load_file(common.SCRIPT_FILE)
    g_script["body"] = sorted(g_script["body"], key=itemgetter("seq"))
    fn_display_info(" Script - Header ", g_script["header"])
    fn_display_info(" Script - Body ", g_script["body"])

    g_process["standby_proc_list"] = copy.deepcopy(g_script["body"])


@add_object_info()
def fn_process_next(is_error=False, err_msg=""):
    global g_process

    if is_error:
        g_process["current_proc"] = {"name": "error", "data": {"name": g_process["current_proc"]["name"], "msg": err_msg}}
    else:
        if 0 < len(g_process["standby_proc_list"]):
            g_process["current_proc"] = g_process["standby_proc_list"].pop(0)
        else:
            g_process["result"]["result"] = "OK"
            g_process["current_proc"] = {"name": "result", "data": {"result": g_process["result"]}}


@add_object_info()
def fn_process_set_result(current_result):
    global g_process

    for key in current_result:
        if "detail" == key:
            detail = current_result["detail"]
            for d in detail:
                g_process["result"]["detail"][d] = detail[d]
        elif "start_time" == key:
            g_process["start_time"] = current_result[key]
        else:
            g_process["result"][key] = current_result[key]


@add_object_info()
def fn_jig_hw_init():
    #gpio.output(GOPS_RESET, CTRL_ON)
    gpio.output(GOPS_SWITCHED_PWR, POWER_OFF)
    gpio.output(GOPS_CYLINDER, CTRL_UP)
    time.sleep(DELAY_CTRL_CYLINDER)
    gpio.output(GOPS_FU, CTRL_UP)
    time.sleep(DELAY_CTRL_FU)


@add_object_info()
def fn_tag_reset():
    """
    gpio.output(GOPS_RESET, CTRL_OFF)
    time.sleep(DELAY_RESET_TAG)
    gpio.output(GOPS_RESET, CTRL_ON)
    time.sleep(DELAY_RESET_TAG)
    """
    mcu = g_script["header"]["mcu"]
    result = fn_jlink("RESET", mcu, None)


@add_object_info()
def fn_test_start(fn_data):
    #leds = [GOPS_TEST_OK, GOPS_TEST_NG, GOPS_ETH_OK, GOPS_ETH_NG, GOPS_DN_OK, GOPS_DN_NG, GOPS_RF_OK, GOPS_RF_NG,
    leds = [GOPS_ETH_OK, GOPS_ETH_NG, GOPS_DN_OK, GOPS_DN_NG, GOPS_RF_OK, GOPS_RF_NG,
            GOPS_NFC_OK, GOPS_NFC_NG, GOPS_MAC_OK, GOPS_MAC_NG]

    # check tag & start button
    if (STATUS_ON == g_input_pin["g_chk_tag"]) and (STATUS_ON == g_input_pin["g_chk_fu"]) and ("TESTING" == g_test_status):
        g_logger.debug("fn_test_start > AUTO TEST :: START.")

        # init led and tag power on
        fn_clear_led(leds)
        gpio.output(GOPS_SWITCHED_PWR, POWER_ON)
		
        g_logger.debug("fn_test_start > PROCESS :: LOAD.")
        fn_process_load()
        fn_process_set_result({"start_time": datetime.datetime.now()})
        fn_process_next()
    else:
        time.sleep(DELAY_GLOBAL)

		
@add_object_info()
def fn_jlink(jcmd, device, filename):
    #cmd = 'cd \home\MP\jlink\n./JLinkExe\nsleep 100\nspeed 4000\nsleep 100\nsi SWD\nsleep 100\ndevice {}\nsleep 100\nconnect\n'.format(device)
    #cmd = 'speed 4000\nsleep 200\nsi SWD\nsleep 200\ndevice efr32fg1vxxxf256\nsleep 200\n'
    cmd = ''
	
    if jcmd == 'RESET':
        cmd += 'r\nexit\n'
        g_logger.info("fn_jlink > reset")			
    else:
        cmd += 'loadbin {0} 0\nsleep 200\nverifybin {0} 0\nsleep 200\nr\nexit\n'.format(filename)
        g_logger.info("fn_jlink > download")

    g_logger.info("fn_jlink > jcmd :: {}, device :: {}, filename :: {}".format(jcmd, device, filename))
    #p = Popen(['/home/MP/jlink/JLinkExe'], stdin=PIPE, stdout=PIPE)
    #p = Popen([PATH_JLINK + 'JLinkExe', '-if', 'SWD', '-speed', '4000', '-device', 'efm32gg330f1024'], stdin=PIPE, stdout=PIPE)
    p = Popen([PATH_JLINK + 'JLinkExe', '-if', 'SWD', '-speed', '4000', '-device', device], stdin=PIPE, stdout=PIPE)
    out = p.communicate(input=bytearray(cmd, 'utf-8'))[0]
    out = out.decode('utf-8')
    rst = -1 #'NG'

    if jcmd == 'RESET':
        if out.find('SYSRESETREQ has confused core') < 0 :
            rst = 0 #'OK'
    else:
        if out.find('Contents already match') > 0:
            rst = 0 #'OK (SKIPPED)'
        elif out.find('Verify successful') > 0:
            rst = 0 #'OK'

    return rst
	
	
@add_object_info()
def fn_download(fn_data):
    current_proc = g_process["current_proc"]
    if current_proc["enable"] == "no":
        g_logger.info("fn_download > DOWNLOAD :: NT")
        fn_process_set_result({"detail": {"download": "NT"}})
        fn_process_next()
    else:
        result = -1

        file_name = fn_data["file"]
        mcu = g_script["header"]["mcu"]
        for i in range(current_proc["retry"] + 1):
            fn_tag_reset()
            
            result = fn_jlink("DOWNLOAD", mcu, "{}{}".format(common.TAG_IMG_PATH, file_name))
            #result = os.system("./swdp {}{} 0 1".format(common.TAG_IMG_PATH, file_name))
            #result = os.system("./fuse")

            if 0 == result:
                g_logger.info("fn_download > DOWNLOAD :: OK")
                fn_process_set_result({"detail": {"download": "OK"}})
                fn_process_next()
                gpio.output(GOPS_DN_OK, CTRL_LED_ON)
                gpio.output(GOPS_DN_NG, CTRL_LED_OFF)
                break
				
        if 0 != result:
            g_logger.info("fn_download > DOWNLOAD :: NG")
            fn_process_set_result({"detail": {"download": "NG"}})
            fn_process_next(is_error=True, err_msg="download :: NG")
            gpio.output(GOPS_DN_OK, CTRL_LED_OFF)
            gpio.output(GOPS_DN_NG, CTRL_LED_ON)


@add_object_info()
def fn_write_mac(fn_data):
    tagMac = None
    w_result = False
    sel_led = None

    current_proc = g_process["current_proc"]
    if current_proc["enable"] == "no":
        g_logger.info("fn_write_mac > WRITE MAC :: NT")
        fn_process_set_result({"detail": {"writeMac": "NT"}})
        fn_process_next()
    else:
        try:
            result, resp_data = fn_web_tx_get_tag_mac()
            g_logger.debug("fn_write_mac > result :: {}, resp_data :: {}".format(result, resp_data))
            if False == result:
                sel_led = "ethernet"
                raise CMpError("fn_write_mac > Not received mac address from server.")
            else:
                tagMac = resp_data["tagMac"]
                gpio.output(GOPS_ETH_OK, CTRL_LED_ON)
                gpio.output(GOPS_ETH_NG, CTRL_LED_OFF)

            for i in range(current_proc["retry"] + 1):
                g_logger.debug("fn_write_mac > {}".format("TAG POWER :: OFF -> ON"))
                fn_tag_reset()

                g_logger.debug("fn_write_mac > MAC :: WRITE")
                reverse_data = bytearray.fromhex(resp_data["tagMac"][:6] + "FFFE" + resp_data["tagMac"][6:])
                reverse_data.reverse()
                cs = sum(reverse_data) + sum(bytearray(resp_data['abstractMac'].encode('ascii'))) + sum(bytearray(g_script["header"]['tag_type'].encode('ascii')))

                tx_data = bytearray(b'macmacf') + reverse_data + bytearray(resp_data['abstractMac'].encode('ascii') + g_script["header"]["tag_type"].encode('ascii'))
                tx_data += bytearray.fromhex("%02x" % ((cs >> 8) & 0xFF) + ("%02x" % (cs & 0xFF)) + g_script["header"]["tag_type"])
                w_result, rx_data, rest_time = fn_serial_send_data(tx_data, current_proc["timeout"], True)
                g_logger.debug("fn_write_mac > result :: {}, rx_data :: {}, rest_time :: {}, tx_data :: {}".format(w_result, rx_data, rest_time, tx_data))

                if w_result:
                    g_logger.info("fn_write_mac > WRITE MAC :: OK")
                    fn_process_set_result({"tagMac": resp_data["tagMac"], "detail": {"writeMac": "OK"}})
                    fn_process_next()
                    gpio.output(GOPS_MAC_OK, CTRL_LED_ON)
                    gpio.output(GOPS_MAC_NG, CTRL_LED_OFF)
                    break

            if False == w_result:
                sel_led = "write_mac"
                raise CMpError("fn_write_mac > Fail to write mac address.")
        except CMpError as e:
            g_logger.error(e)
            g_logger.info("fn_write_mac > WRITE MAC :: NG")
            fn_process_set_result({"tagMac": tagMac, "detail": {"writeMac": "NG"}})
            fn_process_next(is_error=True, err_msg="write_mac :: NG")
            if "ethernet" == sel_led:
                gpio.output(GOPS_ETH_OK, CTRL_LED_OFF)
                gpio.output(GOPS_ETH_NG, CTRL_LED_ON)
            else:
                gpio.output(GOPS_MAC_OK, CTRL_LED_OFF)
                gpio.output(GOPS_MAC_NG, CTRL_LED_ON)


@add_object_info()
def fn_nfc(fn_data):
    current_proc = g_process["current_proc"]
    if current_proc["enable"] == "no":
        g_logger.info("fn_nfc > NFC :: NT")
        fn_process_set_result({"detail": {"nfc": "NT"}})
        fn_process_next()
    else:
        g_logger.debug("fn_nfc > {}".format("TAG POWER :: OFF -> ON"))
        fn_tag_reset()

        g_logger.debug("fn_nfc > NFC :: WRITE")
        nfc_data = fn_data["nfc_data"]
        tx_data = bytearray(b'nfc') + bytearray.fromhex("%02x" % (len(nfc_data) + 1)) + bytearray.fromhex("%02x" % 0) + bytearray(nfc_data.encode('ascii'))
        w_result, rx_data, rest_time = fn_serial_send_data(tx_data, current_proc["timeout"], True)
        g_logger.debug("fn_nfc > result :: {}, rx_data :: {}, rest_time :: {}, tx_data :: {}".format(w_result, rx_data, rest_time, tx_data))

        if w_result:
            g_logger.info("fn_nfc > NFC :: OK")
            fn_process_set_result({"detail": {"nfc": "OK"}})
            fn_process_next()
            gpio.output(GOPS_NFC_OK, CTRL_LED_ON)
            gpio.output(GOPS_NFC_NG, CTRL_LED_OFF)
        else:
            g_logger.info("fn_nfc > NFC :: NG")
            fn_process_set_result({"detail": {"nfc": "NG"}})
            fn_process_next(is_error=True, err_msg="nfc :: NG")
            gpio.output(GOPS_NFC_OK, CTRL_LED_OFF)
            gpio.output(GOPS_NFC_NG, CTRL_LED_ON)


@add_object_info()
def fn_rf(fn_data):
    detail_data=[]
    for i in range(len(fn_data["ch"])):
        ch = fn_data["ch"][i]
        detail_data.append({"ch": str(ch), "txPower": "", "freqErr": "", "evm": ""})

    current_proc = g_process["current_proc"]
    if current_proc["enable"] == "no":
        g_logger.info("fn_rf > RF :: NT")
        fn_process_set_result({"detail": {"rfTest": "NT"}})
        fn_process_next()
    else:
        try:
            if STATUS_CYLINDER_DOWN == g_input_pin["g_chk_cylinder"]:
                model = g_script["header"]["model"]
                			
                for i in range(len(fn_data["ch"])):
                    ch = fn_data["ch"][i]
                    tag_power = g_env["rf"][model][str(ch)]["tag_power"]	
                    loss = g_env["rf"][model][str(ch)]["loss"]
                    # add code :: test rf
                    g_logger.debug("fn_test_rf > {}".format("TAG POWER :: ON -> OFF -> ON"))
                    fn_tag_reset()

                    g_logger.debug("fn_test_rf > RF :: {}ch".format(ch))
                    tx_data = bytearray(b'evm') + bytearray.fromhex(("%02x" % ch) + ("%02x" % (ch ^ 0xFF)))
                    w_result, rx_data, rest_time = fn_serial_send_data(tx_data, current_proc["timeout"], False)
                    g_logger.debug("fn_test_rf > result :: {}, rx_data :: {}, rest_time :: {}, tx_data :: {}".format(w_result, rx_data, rest_time, tx_data))

                    power, offset_evm, freq_error = fn_ni_measure_rf(g_env["ni"]["ip"], g_env["ni"]["port"], g_freq_list[ch], tag_power, loss, current_proc["timeout"])
                    detail_data[i]["txPower"] = power
                    detail_data[i]["freqErr"] = offset_evm
                    detail_data[i]["evm"] = freq_error

                    if fn_data["threshold_power"] > float(detail_data[i]["txPower"]):
                        raise CMpError("fn_rf > {} :: Out of threshold range(Power) :: {}.".format(ch, detail_data[i]["txPower"]))

                    if fn_data["threshold_evm"] < float(detail_data[i]["freqErr"]):
                        raise CMpError("fn_rf > {} :: Out of threshold range(Evm) :: {}.".format(ch, detail_data[i]["freqErr"]))

                    if (fn_data["threshold_min_freq_err"] > float(detail_data[i]["evm"])) or (fn_data["threshold_max_freq_err"] < float(detail_data[i]["evm"])):
                        raise CMpError("fn_rf > {} :: Out of threshold range(Freq Err) :: {}.".format(ch, detail_data[i]["evm"]))

                # {"ch": "11", "txPower": 0, "freqErr": 0, "evm": 0}
                g_logger.info("fn_rf > RF :: OK")
                fn_process_set_result({"detail": {"rfTest": {"result": "OK", "data": detail_data}}})
                fn_process_next()
                gpio.output(GOPS_RF_OK, CTRL_LED_ON)
                gpio.output(GOPS_RF_NG, CTRL_LED_OFF)
            else:
                fn_process_next(is_error=True, err_msg="cylinder :: OPEN")
        except CMpError as e:
            g_logger.error(e)
            g_logger.info("fn_rf > RF :: NG")
            fn_process_set_result({"detail": {"rfTest": {"result": "NG", "data": detail_data}}})
            fn_process_next(is_error=True, err_msg="rfTest :: NG")
            gpio.output(GOPS_RF_OK, CTRL_LED_OFF)
            gpio.output(GOPS_RF_NG, CTRL_LED_ON)

@add_object_info()
def fn_result(fn_data):
    g_logger.debug("fn_result > g_process :: {}".format(g_process))

    result, resp_data = fn_web_tx_result()
    g_logger.debug("fn_result > result :: {}, resp_data :: {}".format(result, resp_data))

    fn_jig_hw_init()
    fn_process_reset()


@add_object_info()
def fn_error(fn_data):
    g_logger.debug("fn_error > g_process :: {}".format(g_process))

    #if "write mac" == g_process["current_proc"]["data"]["name"]:
    result, resp_data = fn_web_tx_result()
    g_logger.debug("fn_error > result :: {}, resp_data :: {}".format(result, resp_data))

    g_logger.debug("fn_error > Press reset button.")
    while STATUS_ON != g_input_pin["g_chk_reset"]:
        if (STATUS_ON != g_input_pin["g_chk_fu"]) or (STATUS_CYLINDER_DOWN != g_input_pin["g_chk_cylinder"]):
            break
        time.sleep(DELAY_GLOBAL)

    g_logger.debug("fn_error > Init Jig")
    fn_jig_hw_init()
    fn_process_reset()


########################################################
# main
if __name__ == '__main__':
    proc_list = {
        "test start": fn_test_start,
        "download": fn_download,
        "write mac": fn_write_mac,
        "nfc": fn_nfc,
        "rf": fn_rf,
        "result": fn_result,
        "error": fn_error
    }

    # start program
    loop = fn_program_start()

    while loop:
        try:
            if "normal" == g_process["mode"]:
                proc_name = g_process["current_proc"]["name"]
                proc_data = g_process["current_proc"]["data"]
                if (proc_name == g_process["current_proc"]["name"]) and (proc_name in proc_list):
                    proc_list[proc_name](proc_data)
                elif proc_name in ["result", "error"]:
                    proc_list[proc_name](proc_data)
                else:
                    g_logger.warn("Main > Unknown process name :: {}, current proc :: {}".format(proc_name, g_process["current_proc"]))

                time.sleep(DELAY_GLOBAL * 10)
            else:
                time.sleep(DELAY_GLOBAL)
                g_logger.warn("Main > Unknown process mode :: {}".format(g_process["mode"]))
        except Exception:
            tb = traceback.format_exc()
            msg = "\r\n{:*^57}\r\n{}\r\n{}".format("[Error-MP]", tb, "-" * 57)
            g_logger.exception(msg)

            #loop = False
            fn_process_next(is_error=True, err_msg="PROGRAM BUG :: OCCUR.")

    # end program
    fn_program_end()
