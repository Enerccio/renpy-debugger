from __future__ import print_function

import os
import sys
import threading
import socket
import json
import traceback
import types
import time

from librpydb.baseconf import DEBUGGER_PORT
from librpydb.utils import NoneDict
from librpydb.dis import dis
from librpydb.protocol import *


# Holds the instance of renpy debugger if debug mode is on
debugger = None
# instance of debug handler,
handler = None


class DebugAdapterProtocolServer(threading.Thread):
    """
    Protocol handler server

    This server will server single client only, rest will have to wait until
    client has disconnected.

    This will start listening in a new thread
    """

    def __init__(self):
        super(DebugAdapterProtocolServer, self).__init__(name="DAP")
        self.daemon = True
        self._current_client = None
        # True if there is client connected whom is all set up
        self._ready_for_events = False

        self.start()

    def is_client_attached(self):
        return self._ready_for_events

    def run(self):
        """
        Starts the handler server
        """

        listen_port = DEBUGGER_PORT if "RENPY_DEBUGGER_PORT" not in os.environ else os.environ["RENPY_DEBUGGER_PORT"]

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", listen_port))
        server.listen(0)

        while True:
            client, client_address = server.accept()
            self.attach_one_client(client)

    def attach_one_client(self, csocket):
        """
        Attaches single client to the debugging
        """

        self._current_client = csocket
        self.next_seq = 0

        # manual requests

        self.enter_read_loop()

    def enter_read_loop(self):
        """
        This thread blocks and waits for messages from current client
        """

        try:
            while True:
                try:
                    request = DAPMessage.recv(self._current_client)
                except Exception as e:
                    # TODO send error
                    traceback.print_exc()
                    continue

                if request is None:
                    # client terminated without termination request
                    return
                try:
                    self.resolve_message(request)
                except Exception as e:
                    # TODO send error
                    traceback.print_exc()
                    continue

                if self._current_client is None:
                    self._ready_for_events = False
                    return  # terminated

        except BaseException as e:
            # failure while communicating
            traceback.print_exc()
            pass
        finally:
            # final handler, clear active client
            self._current_client = None
            self._ready_for_events = False

            debugger.reset()

    def resolve_message(self, rq):
        """
        Main message resolving function

        Resolves the message from client, changing debug state as appropriate, returning responses
        """

        if rq.command == "initialize":
            DAPInitializeResponse(rq.seq, features).set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
            DAPInitializedEvent().set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
        elif rq.command == "setBreakpoints":
            bkps = self.create_breakpoints(**rq.kwargs)
            self.next_seq += 1
            DAPSetBreakpointsResponse(rq.seq, [b.serialize() for b in bkps]).set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
        elif rq.command == "configurationDone":
            DAPResponse(rq.seq, "configurationDone").set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
            self._ready_for_events = True
        elif rq.command == "launch":
            # no special noDebug
            DAPResponse(rq.seq, "launch").set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
        elif rq.command == "disconnect":
            DAPResponse(rq.seq, "disconnect").set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
            self._current_client.close()
            self._current_client = None
            return
        elif rq.command == "continue":
            DAPContinueResponse(rq.seq, all_threads_continue=True).set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
            debugger.stepping = SteppingMode.STEP_NO_STEP
            debugger.continue_next()
        elif rq.command == "threads":
            DAPThreadsResponse(rq.seq, [{"id": 0, "name": "renpy_main"}]).set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
        elif rq.command == "stackTrace":
            DAPStackTraceResponse(rq.seq, debugger.get_stack_frames(**rq.kwargs)).set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
        elif rq.command == "scopes":
            DAPScopesResponse(rq.seq, debugger.get_scopes(int(rq.kwargs["frameId"]))).set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
        elif rq.command == "variables":
            DAPVariablesResponse(rq.seq, debugger.format_variable(**rq.kwargs)).set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
        elif rq.command == "pause":
            DAPResponse(rq.seq, "pause").set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
            debugger.break_pause = True
        elif rq.command == "next":
            DAPResponse(rq.seq, "next").set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
            debugger.store_frames()
            debugger.stepping = SteppingMode.STEP_NEXT
            debugger.continue_next()
        elif rq.command == "stepIn":
            DAPResponse(rq.seq, "stepIn").set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
            debugger.store_frames()
            debugger.stepping = SteppingMode.STEP_INTO
            debugger.continue_next()
        elif rq.command == "stepOut":
            DAPResponse(rq.seq, "stepOut").set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1
            debugger.store_frames()
            debugger.stepping = SteppingMode.STEP_OUT
            debugger.continue_next()
        else:
            DAPErrorResponse(rqs=rq.seq, command=rq.command, message="NotImplemented").set_seq(self.next_seq).send(self._current_client)
            self.next_seq += 1

    def create_breakpoints(self, source, breakpoints=[], lines=[], sourceModified=False):
        """
        Creates breakpoints from request
        """

        # print("Synchronizing breakpoints for source=%s, bkps=%s" % (str(source), str(breakpoints)))
        path = source["path"]
        created_breakpoints = []

        debugger.clear_source_breakpoints(path)

        for bkp_info in breakpoints:
            line = bkp_info["line"]
            condition = bkp_info["condition"]
            hit_condition = bkp_info["hitCondition"]
            if hit_condition is not None:
                hit_condition = int(hit_condition)
            # log message not suppored (yet?)

            breakpoint = Breakpoint(path, line, eval_condition=condition, counter=hit_condition)
            debugger.register_breakpoint(breakpoint)
            created_breakpoints.append(breakpoint)

        return created_breakpoints

    def send_breakpoint_event(self, breakpoint):
        self.pause_debugging()

    def pause_debugging(self):
        """
        Sends message to client that debug state has been paused
        """

        DAPStoppedEvent(reason=debugger.pause_reason, description=debugger.frame_location_info(),
                        thread_id=0, preserve_focus_hint=False,
                        all_threads_stopped=True).set_seq(self.next_seq).send(self._current_client)
        self.next_seq += 1


class Breakpoint(object):
    """
    Breakpoint information
    """

    def __init__(self, source, line, eval_condition=None, counter=None):
        self.source = source
        self.line = int(line) if isinstance(line, str) else line
        self.eval_condition = eval_condition
        self.counter = counter
        self.times_hit = 0

    def serialize(self):
        """
        Stub method to send information about breakpoint back to client
        """

        data = {}

        data["verified"] = True

        return data

    def applies(self, frame):
        """
        Checks whether this breakpoint applies to this frame
        """

        if frame.f_code.co_filename == self.source and frame.f_lineno == self.line:
            # breakpoint hits, now try eval if it is eval

            eval_passed = True
            if self.eval_condition is not None:
                eval_passed = False
                try:
                    if eval(self.eval_condition, frame.f_globals, frame.f_locals):
                        # so eval_passed is boolean not whatever eval returned, it is in separate if!
                        eval_passed = True
                except BaseException:
                    # eval failure, ignore
                    pass

            if eval_passed:
                # eval passed, check for counter
                self.times_hit += 1

                if self.counter is None or self.counter < self.times_hit:
                    return True

        return False


class SteppingMode(object):
    """
    Stepping mode enum
    """

    STEP_NO_STEP = 0
    """
    No stepping is active
    """

    STEP_NEXT = 1
    """
    Stepping into next line is active
    """

    STEP_INTO = 2
    """
    Stepping into next call is active
    """

    STEP_OUT = 3
    """
    Stepping out of call is active
    """

    # special case that will break next time anything is called!
    STEP_SINGLE_EXEC = 99
    """
    Step into next line frame, wherever it is
    """


class RenpyPythonDebugger(object):
    """
    RenpyPythonDebugger

    Contains debugging state and debugs renpy
    """

    def __init__(self):
        super(RenpyPythonDebugger, self).__init__()

        # set of active breakpoints
        self.active_breakpoints = set()
        # breakpoints set modification lock
        self.bkp_lock = threading.Lock()

        # active stepping mode
        self.stepping = SteppingMode.STEP_NO_STEP
        # cont is main spinlock, when False, state is paused
        self.cont = True
        # why was renpy execution paused is stored here and reported to client
        self.pause_reason = None
        # break on cont failure reasons
        #  pause was asked
        self.break_pause = False

        # holds paths to variables for each scope opened
        # scope assign containts tuples (value, parent_accessor, type (None for scope), parent_object)
        self.scope_assign = {}
        # current break var id generator (0->more)
        self.scope_var_id = 0

        # current active call frame
        self.active_call = None
        # current active line frame
        self.active_frame = None
        # stored frames when stepping happens, used to differentiate where to step
        self.stored_frames = None

    def store_frames(self):
        """
        stores active call and line frame in stored_frames
        """
        self.stored_frames = (self.active_call, self.active_frame)

    def reset(self):
        """
        resets state of the debugging

        called when client disconnects
        """
        with self.bkp_lock:
            self.active_breakpoints = set()
            self.stepping = SteppingMode.STEP_NO_STEP
            self.continue_next()

    def continue_next(self):
        """
        resumes execution, clearing any scope info
        """

        self.scope_assign = {}
        self.scope_var_id = 0
        self.cont = True

    def attach(self):
        """
        attaches itself into renpy and begins tracing
        """
        sys.settrace(self.trace_event)

    def trace_event(self, frame, event, arg):
        """
        tracing function for non line events
        """

        self.active_frame = frame
        self.active_call = frame

        if event == "call":
            frame.f_trace = self.trace_line

        self.base_trace(frame, event, arg)

    def trace_line(self, frame, event, arg):
        """
        trace function for line events
        """

        self.active_frame = frame

        self.base_trace(frame, event, arg)

    def base_trace(self, frame, event, arg):
        """
        main tracing method, called on every frame of execution including special events
        """

        # print("Tracing %s %s %s (%s))" % (event, "<File %s, Line %s>" % (frame.f_code.co_filename, frame.f_lineno), str(arg), str(id(threading.current_thread()))))

        # if true, breakpoints will be checked
        test_breakpoints = True

        # check for steppings
        if self.stepping != SteppingMode.STEP_NO_STEP:
            # print("Tracing for %s %s %s %s (%s))" % (str(self.stepping), event, "<File %s, Line %s>" % (frame.f_code.co_filename, frame.f_lineno), str(arg), str(id(threading.current_thread()))))

            # single execution step, to move out of return/call frames into line frames
            if self.stepping == SteppingMode.STEP_SINGLE_EXEC:
                test_breakpoints = False
                self.stepping = SteppingMode.STEP_NO_STEP
                self.break_pause = False
                self.cont = False
                handler.pause_debugging()

            # step INTO and call happens on same level as we are, we are in
            # just move one step to line
            if self.stepping == SteppingMode.STEP_INTO and self.active_frame.f_back is self.stored_frames[1] and event == "call":
                # this will exit because call is unhandled!
                test_breakpoints = False
                self.stepping = SteppingMode.STEP_SINGLE_EXEC
                self.pause_reason = "stepIn"

            # step INTO but there is nothing to go in
            # so only move as step
            if self.stepping == SteppingMode.STEP_INTO and self.active_frame is self.stored_frames[1] and event != "return":
                self.stepping = SteppingMode.STEP_NEXT

            # same as above but we are returning, so do single step to move out
            if self.stepping == SteppingMode.STEP_INTO and self.active_frame is self.stored_frames[1] and event != "return":
                test_breakpoints = False
                self.stepping = SteppingMode.STEP_SINGLE_EXEC
                self.pause_reason = "step"

            # step OUT and return happens, just move one step to line
            if self.stepping == SteppingMode.STEP_OUT and self.active_frame is self.stored_frames[1] and event == "return":
                test_breakpoints = False
                self.stepping = SteppingMode.STEP_SINGLE_EXEC
                self.pause_reason = "stepOut"
                return  # exit evaluation

            # next will always break if this is line
            if self.stepping == SteppingMode.STEP_NEXT and self.active_frame is self.stored_frames[1] and event != "call":
                test_breakpoints = False
                self.stepping = SteppingMode.STEP_NO_STEP
                self.break_pause = False
                self.pause_reason = "step"
                self.cont = False
                handler.pause_debugging()

        if event == "exception" or event == "call":
            return  # TODO: exceptions, calls

        if test_breakpoints:
            # due to lock we move triggered breakpoint to here
            breaking_on = None

            # check breakpoints under lock
            with self.bkp_lock:
                for breakpoint in self.active_breakpoints:
                    if breakpoint.applies(frame):
                        breaking_on = breakpoint
                        break
            if breaking_on is not None:
                print("Broke at %s %s %s (%s))" % (event, "<File %s, Line %s>" % (frame.f_code.co_filename, frame.f_lineno), str(arg), str(id(threading.current_thread()))))
                self.break_code(breaking_on)  # sets this to blocking

        # check for external requested pause
        if self.break_pause:
            self.break_pause = False
            self.pause_reason = "pause"
            self.cont = False
            handler.pause_debugging()

        while not self.cont:
            # spinlock when we are waiting for debugger
            pass

    def register_breakpoint(self, breakpoint):
        with self.bkp_lock:
            self.active_breakpoints.add(breakpoint)

    def clear_source_breakpoints(self, src):
        with self.bkp_lock:
            new_breakpoints = set()
            for b in self.active_breakpoints:
                if b.source != src:
                    new_breakpoints.add(b)
            self.active_breakpoints = new_breakpoints

    def frame_location_info(self):
        """
        returns location information about current frame

        should be used by other thread when debugged main thread is cont=False
        """

        return str(self.active_frame.f_code.co_filename) + ":" + str(self.active_frame.f_lineno)

    def get_frame(self, frame_ord):
        """
        returns frame with id frame_ord from stack
        """

        cframe = self.active_frame
        c = 0
        while cframe is not None:
            if c == frame_ord:
                return cframe
            cframe = cframe.f_back
            c += 1
        return None

    def get_stack_frames(self, threadId=0, startFrame=0, levels=0, format=None):
        """
        returns stack frames from current execution in DAP format
        """

        # format is ignored, TODO?
        # threadId is ignored since renpy is single threaded for stuff we need

        clevel = 0
        slevel = 0 if startFrame is None else startFrame
        elevel = None if levels is None or levels == 0 else levels

        frames = []
        cframe = self.active_frame
        while cframe is not None:
            if clevel >= slevel:
                finfo = {}

                finfo["id"] = clevel
                finfo["name"] = cframe.f_code.co_name + self.format_method_signature(cframe.f_locals, cframe.f_code)
                finfo["source"] = {"path": cframe.f_code.co_filename }
                finfo["line"] = cframe.f_lineno
                finfo["presentationHint"] = "normal"
                finfo["column"] = 0

                dis_info = {}
                finfo["subsource"] = dis_info

                disassembled = dis(cframe.f_code, cframe.f_lasti)
                dis_info["sources"] = [{"text": self.format_disassembly(cframe.f_lineno, *de), "line": de[1], "source": finfo["source"]} for de in disassembled]
                ord = 0
                for de in disassembled:
                    if de[0]:
                        break
                    ord += 1
                finfo["subsourceElement"] = ord

                frames.append(finfo)
            clevel += 1
            if elevel is not None and clevel >= elevel:
                break
            cframe = cframe.f_back

        return frames

    def format_disassembly(self, cline, current, python_lineno, bytecode_offset, instruction, arg, constant):
        """
        formats disassembly info for single opcode from disassembler
        """

        fmtd = ""

        if bytecode_offset is not None:
            fmtd += str(bytecode_offset) + " "

        fmtd += "[" + instruction + "]"

        if python_lineno is not None:
            fmtd += " at line " + str(python_lineno + cline)

        if arg is not None:
            fmtd += " (%s, %s)" % (str(arg), str(constant))

        return fmtd

    def format_method_signature(self, locals, code):
        """
        formats method signature from code and locals
        """

        res = ""
        is_args = code.co_flags & 4
        is_kwargs = code.co_flags & 8
        total_args = code.co_argcount
        if is_args:
            total_args += 1
        if is_kwargs:
            total_args += 1
        for i in xrange(total_args):
            varname = code.co_varnames[i]

            if is_args and is_kwargs and i == total_args - 2:
                varname = "*" + varname
            elif is_args and is_kwargs and i == total_args - 1:
                varname = "**" + varname
            elif is_args and i == total_args - 1:
                varname = "*" + varname
            elif is_kwargs and i == total_args - 1:
                varname = "**" + varname
            if res == "":
                res = varname
            else:
                res += ", " + varname

        return "(%s)" % res

    def get_scopes(self, frame_ord):
        """
        returns scope information for DAP
        """

        frame = self.get_frame(frame_ord)

        return [self.get_scope(frame, frame.f_locals, "Locals", False), self.get_scope(frame, frame.f_globals, "Globals", True)]

    def get_scope(self, f, scope_dict, name, expensive):
        """
        returns information about scope to DAP
        """

        scope_id = self.scope_var_id
        self.scope_assign[scope_id] = (scope_dict, None, None, None)
        self.scope_var_id += 1

        return {
            "name": name,
            "variablesReference": scope_id,
            "expensive": expensive,
            "namedVariables": len(scope_dict.keys())
        }

    def format_variable(self, variablesReference, filter=None, start=None, count=None, format=None):
        """
        formats variable and any components for variablesReference in DAP format
        """

        # format is ignored, TODO?

        vs = None if start is None or start == 0 else start
        es = None if count is None or count == 0 else count

        var, name, tt, parent = self.scope_assign[variablesReference]

        # print(str(var) + ", " + str(name) + ", " + str(tt))

        is_slotted = False

        if not isinstance(var, dict) and not isinstance(var, list):
            if hasattr(var, "__dict__"):
                var = var.__dict__
            else:
                is_slotted = True

        # print (str(var))

        if not is_slotted and isinstance(var, dict):
            if filter is not None and filter == "indexed":
                return []
            keys = sorted(var.keys())
        elif not is_slotted:
            if filter is not None and filter == "named":
                return []
            keys = range(len(var))
        elif is_slotted:
            keys = dir(var)

        if "self" in keys:
            keys.remove("self")
            keys = ["self"] + keys

        # print (str(keys))

        it = 0
        total = 0
        variables = []
        for vkey in keys:
            if vs is None or it >= vs:
                var_ref = self.scope_var_id
                if is_slotted:
                    value = getattr(var, vkey)
                else:
                    value = var[vkey]

                vardesc = {}
                variables.append(vardesc)

                vardesc["name"] = vkey
                vardesc["value"] = str(value)
                vardesc["type"] = str(type(value))
                # vardesc["presentationHint"] # TODO!!!
                vardesc["evaluateName"] = vkey
                vardesc["variablesReference"] = var_ref

                vv_inner = value
                vv_slotted = False
                if not isinstance(vv_inner, dict) and not isinstance(vv_inner, list):
                    if hasattr(vv_inner, "__dict__"):
                        vv_inner = vv_inner.__dict__
                    else:
                        vv_slotted = True

                if not vv_slotted and isinstance(vv_inner, dict):
                    vardesc["namedVariables"] = len(vv_inner.keys())
                elif not vv_slotted:
                    vardesc["indexedVariables"] = len(vv_inner)
                else:
                    vardesc["namedVariables"] = len(dir(vv_inner))

                self.scope_assign[var_ref] = (value, vkey, str(type(value)), var)

                self.scope_var_id += 1
                total += 1
            it += 1
            if es is not None and total >= es:
                break

        return variables

    def break_code(self, breakpoint):
        """
        breaks code at breakpoint
        """

        self.cont = False
        self.pause_reason = "breakpoint"
        self.scope_assign = {}
        self.scope_var_id = 0
        handler.send_breakpoint_event(breakpoint)


def wait_for_connection():
    """
    spinlock at early execution for debugger client to connect
    """

    while not handler.is_client_attached():
        time.sleep(10)  # spinlock


def attach():
    global debugger, handler
    # initializes and enables debugging

    debugger = RenpyPythonDebugger()
    handler = DebugAdapterProtocolServer()

    # TODO
    # no_wait = "RENPY_DEBUGGER_NOWAIT" in os.environ and os.environ["RENPY_DEBUGGER_NOWAIT"] == "true"
    debugger.attach()
    no_wait = False
    wait_for_connection()
