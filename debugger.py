from __future__ import print_function

import os
import sys
import threading
import socket
import json
import traceback
import types
import time

from opcode import *

# main debugging port
debugger_port = 14711

# Holds the instance of renpy debugger if debug mode is on
debugger = None
# instance of debug handler,
handler = None

# enabled features
features = {
    "supportsExceptionInfoRequest": False,
    "supportTerminateDebuggee": False,
    "supportsTerminateThreadsRequest": False,
    "supportsDataBreakpoints": False,
    "supportsStepInTargetsRequest": False,
    "supportsSetExpression": False,
    "supportsGotoTargetsRequest": False,
    "supportsFunctionBreakpoints": False,

    # TODO
    "supportsConditionalBreakpoints": False,
    "supportsHitConditionalBreakpoints": False,
}

class NoneDict(dict):
    """
    None dict is a dict that returns None on key it does not have
    """

    def __init__(self, other):
        for key in other:
            self[key] = other[key]

    def __getitem__(self, key):
        if key not in self:
            return None
        return dict.__getitem__(self, key)


class DAPMessage(object):
    """
    DAPMessage is base class for all debug adapter protocol
    """

    def __init__(self):
        self.seq = None

    def set_seq(self, seq):
        """
        Sets sequence number to seq
        """

        self.seq = seq
        return self

    @staticmethod
    def recv(socket):
        """
        Retrieves single DAPMessage from socket

        Returns None on failure
        """

        body = DAPMessage.recv_raw(socket)

        if body is not None:
            kwargs = body["arguments"]
            if kwargs is None:
                kwargs = {}
            rq = DAPRequest(command=body["command"], **kwargs)
            rq.set_seq(body["seq"])
            return rq

    @staticmethod
    def recv_raw(socket):
        """
        Retrieves single DAPMessage from socket in raw form (json)

        Returns None on failure
        """

        headers = []

        cread_line = ""

        while True:
            c = socket.recv(1)
            if c == "":
                # end of stream
                return None
            cread_line += c

            if cread_line.endswith("\r\n"):
                if cread_line == "\r\n":
                    break
                else:
                    headers.append(cread_line)
                    cread_line = ""

        headers = DAPMessage.parse_headers(headers)

        content_size = int(headers["Content-Length"])

        data = ""

        while (len(data) < content_size):
            data += socket.recv(content_size-len(data))
            if data == "":
                return None

        body = json.loads(data, object_hook=NoneDict)
        # print("RECEIVED: " + str(body))
        return body

    @staticmethod
    def parse_headers(headers):
        """
        Transforms tags into dict
        """

        h = NoneDict({})
        for hl in headers:
            type, value = hl.split(":")
            type = type.strip()
            value = value.strip()
            h[type] = value
        return h

    def send(self, socket):
        """
        Sends this message to client
        """

        data = self.serialize(self.seq)
        # print("SENT: " + str(data))
        DAPMessage.send_text(socket, data)

    def serialize(self, seq):
        """
        Serializes this message to JSON
        """

        message = {}
        message["seq"] = seq
        message["type"] = self.get_type()

        self.serialize_context(message)

        return json.dumps(message)

    def serialize_context(self, message):
        """
        Serializes inner body of this message

        Abstract method
        """

        pass

    def get_type(self):
        """
        Returns type of this message
        """

        raise NotImplementedError()

    @staticmethod
    def send_text(socket, text):
        """
        Sends the raw text message as DAPMessage
        """

        socket.sendall("Content-Length: " + str(len(text)) + "\r\n")
        socket.sendall("\r\n")
        socket.sendall(text)

    @staticmethod
    def remove_nones(dict):
        """
        Removes all Nones from dict
        """

        d = {}
        for key in dict:
            if dict[key] is not None:
                d[key] = dict[key]
        return d


class DAPRequest(DAPMessage):
    def __init__(self, command, **kwargs):
        self.command = command
        self.kwargs = DAPMessage.remove_nones(kwargs)

    def serialize_context(self, message):
        message["command"] = self.command
        message["args"] = self.kwargs

    def get_type(self):
        return "type"


class DAPEvent(DAPMessage):
    def __init__(self, event):
        self.event = event

    def serialize_context(self, message):
        message["event"] = self.event
        self.serialize_event_context(message)

    def serialize_event_context(self, message):
        raise NotImplementedError()

    def get_type(self):
        return "event"


class DAPResponse(DAPMessage):
    def __init__(self, rqs, command, success=True, message=None):
        self.rqs = rqs
        self.command = command
        self.success = success
        self.message = message

    def serialize_context(self, message):
        message["request_seq"] = self.rqs
        message["command"] = self.command
        message["success"] = self.success
        if self.message is not None:
            message["success"] = self.message
        self.serialize_response_context(message)

    def serialize_response_context(self, message):
        pass

    def get_type(self):
        return "response"


class DAPErrorResponse(DAPResponse):
    def __init__(self, rqs, command, message="", detailed_message=None):
        DAPResponse.__init__(self, rqs, command, success=False, message=message)
        self.dm = detailed_message

    def serialize_response_context(self, message):
        message["body"] = {}
        if self.dm is not None:
            message["body"]["error"] = self.dm


class DAPInitializedEvent(DAPEvent):
    def __init__(self):
        DAPEvent.__init__(self, "initialized")

    def serialize_event_context(self, message):
        pass


class DAPStoppedEvent(DAPEvent):
    def __init__(self, reason, description=None, thread_id=None, preserve_focus_hint=None, text=None, all_threads_stopped=None):
        DAPEvent.__init__(self, "stopped")

        self.reason = reason
        self.description = description
        self.thread_id = thread_id
        self.preserve_focus_hint = preserve_focus_hint
        self.text = text
        self.all_threads_stopped = all_threads_stopped

    def serialize_event_context(self, message):
        body = {}
        message["body"] = body

        body["reason"] = self.reason

        if self.description is not None:
            body["description"] = self.description
        if self.thread_id is not None:
            body["threadId"] = self.thread_id
        if self.preserve_focus_hint is not None:
            body["preserveFocusHint"] = self.preserve_focus_hint
        if self.text is not None:
            body["text"] = self.text
        if self.all_threads_stopped is not None:
            body["allThreadsStopped"] = self.all_threads_stopped


class DAPContinueEvent(DAPEvent):
    def __init__(self, thread_id, all_threads_continue=None):
        DAPEvent.__init__(self, "continued")

        self.thread_id = thread_id
        self.all_threads_continue = all_threads_continue

    def serialize_event_context(self, message):
        body = {}
        message["body"] = body

        body["threadId"] = self.thread_id

        if self.all_threads_continue is not None:
            body["allThreadsContinued"] = self.all_threads_continue


class DAPExitedEvent(DAPEvent):
    def __init__(self, ec):
        DAPEvent.__init__(self, "exited")

        self.ec = ec

    def serialize_event_context(self, message):
        body = {}
        message["body"] = body

        body["exitCode"] = self.ec


class DAPTerminatedEvent(DAPEvent):
    def __init__(self, restart=None):
        DAPEvent.__init__(self, "terminated")

        self.restart = restart

    def serialize_event_context(self, message):
        if self.restart is not None:
            body = {}
            message["body"] = body

            body["restart"] = self.restart


class DAPThreadEvent(DAPEvent):
    def __init__(self, reason, thread_id):
        DAPEvent.__init__(self, "thread")

        self.reason = reason
        self.thread_id = thread_id

    def serialize_event_context(self, message):
        body = {}
        message["body"] = body

        body["reason"] = self.reason
        body["threadId"] = self.thread_id


class DAPOutputEvent(DAPEvent):
    def __init__(self, output, category=None, variables_reference=None, source=None, line=None, column=None, data=None):
        DAPEvent.__init__(self, "output")

        self.output = output
        self.category = category
        self.variables_reference = variables_reference
        self.source = source
        self.line = line
        self.column = column
        self.data = data

    def serialize_event_context(self, message):
        body = {}
        message["body"] = body

        if self.category is not None:
            body["category"] = self.category

        body["output"] = self.output

        if self.variables_reference is not None:
            body["variablesReference"] = self.variables_reference

        if self.source is not None:
            body["source"] = self.source

        if self.line is not None:
            body["line"] = self.line

        if self.column is not None:
            body["column"] = self.column

        if self.data is not None:
            body["data"] = self.data


class DAPBreakpointEvent(DAPEvent):
    def __init__(self, reason, breakpoint):
        DAPEvent.__init__(self, "breakpoint")

        self.reason = reason
        self.breakpoint = breakpoint

    def serialize_event_context(self, message):
        body = {}
        message["body"] = body

        body["reason"] = self.reason
        body["breakpoint"] = self.breakpoint


class DAPModuleEvent(DAPEvent):
    def __init__(self, reason, module):
        DAPEvent.__init__(self, "module")

        self.reason = reason
        self.module = module

    def serialize_event_context(self, message):
        body = {}
        message["body"] = body

        body["reason"] = self.reason
        body["module"] = self.module


class DAPLoadedSourceEvent(DAPEvent):
    def __init__(self, reason, source):
        DAPEvent.__init__(self, "loadedSource")

        self.reason = reason
        self.source = source

    def serialize_event_context(self, message):
        body = {}
        message["body"] = body

        body["reason"] = self.reason
        body["source"] = self.source


class DAPProcessEvent(DAPEvent):
    def __init__(self, name, process_id=None, is_local=None, start_method=None):
        DAPEvent.__init__(self, "process")

        self.name = name
        self.process_id = process_id
        self.is_local = is_local
        self.start_method = start_method

    def serialize_event_context(self, message):
        body = {}
        message["body"] = body

        body["name"] = self.name

        if self.process_id is not None:
            body["systemProcessId"] = self.process_id

        if self.is_local is not None:
            body["isLocalProcess"] = self.is_local

        if self.start_method is not None:
            body["startMethod"] = self.start_method


class DAPCapabilitiesEvent(DAPEvent):
    def __init__(self, capabilities):
        DAPEvent.__init__(self, "capabilities")

        self.capabilities = capabilities

    def serialize_event_context(self, message):
        body = {}
        message["body"] = body

        body["capabilities"] = self.capabilities


class DAPRunInTerminalRequest(DAPRequest):
    def __init__(self, cwd, args, kind=None, title=None, env=None):
        DAPRequest.__init__(self, "runInTerminal", kind, title, cwd, args, env)


class DAPRunInTerminalResponse(DAPResponse):
    def __init__(self, rqs, process_id=None, shell_process_id=None):
        DAPResponse.__init__(self, rqs, "runInTerminal")
        self.process_id = process_id
        self.shell_process_id = shell_process_id

    def serialize_response_context(self, message):
        body = {}
        message["body"] = body

        if self.process_id is not None:
            body["processId"] = self.process_id

        if self.shell_process_id is not None:
            body["shellProcessId"] = self.shell_process_id


### ONLY SUPPORTED RESPONSES (and thus requests) ARE IMPLEMENTED!

class DAPSetBreakpointsResponse(DAPResponse):
    def __init__(self, rqs, breakpoints):
        DAPResponse.__init__(self, rqs, "setBreakpoints")
        self.breakpoints = breakpoints

    def serialize_response_context(self, message):
        body = {}
        message["body"] = body

        body["breakpoints"] = self.breakpoints


class DAPSetFunctionBreakpointsResponse(DAPResponse):
    def __init__(self, rqs, breakpoints):
        DAPResponse.__init__(self, rqs, "setFunctionBreakpoints")
        self.breakpoints = breakpoints

    def serialize_response_context(self, message):
        body = {}
        message["body"] = body

        body["breakpoints"] = self.breakpoints


class DAPContinueResponse(DAPResponse):
    def __init__(self, rqs, all_threads_continue=None):
        DAPResponse.__init__(self, rqs, "continue")
        self.all_threads_continue = all_threads_continue

    def serialize_response_context(self, message):
        body = {}
        message["body"] = body

        if self.all_threads_continue is not None:
            body["allThreadsContinued"] = self.all_threads_continue

# next has no special response

# step has no special response

# step out has no special response

# pause has no special response

class DAPInitializeResponse(DAPResponse):
    def __init__(self, rqs, capabilities):
        DAPResponse.__init__(self, rqs, "initialize")
        self.capabilities = capabilities

    def serialize_response_context(self, message):
        body = {}
        message["body"] = self.capabilities


class DAPStackTraceResponse(DAPResponse):
    def __init__(self, rqs, stack_frames):
        DAPResponse.__init__(self, rqs, "stackTrace")
        self.stack_frames = stack_frames

    def serialize_response_context(self, message):
        body = {}
        message["body"] = body

        body["stackFrames"] = self.stack_frames
        body["totalFrames"] = len(self.stack_frames)


class DAPScopesResponse(DAPResponse):
    def __init__(self, rqs, scopes):
        DAPResponse.__init__(self, rqs, "scopes")
        self.scopes = scopes

    def serialize_response_context(self, message):
        body = {}
        message["body"] = body

        body["scopes"] = self.scopes


class DAPVariablesResponse(DAPResponse):
    def __init__(self, rqs, variables):
        DAPResponse.__init__(self, rqs, "variables")
        self.variables = variables

    def serialize_response_context(self, message):
        body = {}
        message["body"] = body

        body["variables"] = self.variables


class DAPSetVariableResponse(DAPResponse):
    def __init__(self, rqs, value, type=None, variables_reference=None, named_variables=None, indexed_variables=None):
        DAPResponse.__init__(self, rqs, "setVariable")
        self.value = value
        self.type = type
        self.variables_reference = variables_reference
        self.named_variables = named_variables
        self.indexed_variables = indexed_variables

    def serialize_response_context(self, message):
        body = {}
        message["body"] = body

        body["value"] = self.value
        if self.type is not None:
            body["type"] = self.type
        if self.variables_reference is not None:
            body["variablesReference"] = self.variables_reference
        if self.named_variables is not None:
            body["namedVariables"] = self.named_variables
        if self.indexed_variables is not None:
            body["indexedVariables"] = self.indexed_variables


class DAPSourceResponse(DAPResponse):
    def __init__(self, rqs, source, mime_type=None):
        DAPResponse.__init__(self, rqs, "source")
        self.source = source
        self.mime_type = mime_type

    def serialize_response_context(self, message):
        body = {}
        message["body"] = body

        body["source"] = self.source
        if self.mime_type is not None:
            body["mimeType"] = self.mime_type


class DAPThreadsResponse(DAPResponse):
    def __init__(self, rqs, threads):
        DAPResponse.__init__(self, rqs, "threads")
        self.threads = threads

    def serialize_response_context(self, message):
        body = {}
        message["body"] = body

        body["threads"] = self.threads


class DAPEvaluateResponse(DAPResponse):
    def __init__(self, rqs, result, type=None, presentation_hint=None, variables_reference=None, named_variables=None, indexed_variables=None):
        DAPResponse.__init__(self, rqs, "evaluate")
        self.result = result
        self.type = type
        self.presentation_hint = presentation_hint
        self.variables_reference = variables_reference
        self.named_variables = named_variables
        self.indexed_variables = indexed_variables

    def serialize_response_context(self, message):
        body = {}
        message["body"] = body

        body["value"] = self.value
        if self.type is not None:
            body["type"] = self.type
        if self.presentation_hint is not None:
            body["presentationHint"] = self.presentation_hint
        if self.variables_reference is not None:
            body["variablesReference"] = self.variables_reference
        if self.named_variables is not None:
            body["namedVariables"] = self.named_variables
        if self.indexed_variables is not None:
            body["indexedVariables"] = self.indexed_variables


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

        listen_port = debugger_port if "RENPY_DEBUGGER_PORT" not in os.environ else os.environ["RENPY_DEBUGGER_PORT"]

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
                    return # terminated

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
                except:
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
                return # exit evaluation

            # next will always break if this is line
            if self.stepping == SteppingMode.STEP_NEXT and self.active_frame is self.stored_frames[1] and event != "call":
                test_breakpoints = False
                self.stepping = SteppingMode.STEP_NO_STEP
                self.break_pause = False
                self.pause_reason = "step"
                self.cont = False
                handler.pause_debugging()

        if event == "exception" or event == "call":
            return # TODO: exceptions, calls

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
                self.break_code(breaking_on) # sets this to blocking

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
                finfo["source"] = {"path" : cframe.f_code.co_filename }
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


# disassembler - sane one

class DisElement(object):
    """
    holds disassembler instruction information
    """

    def __init__(self):
        self.py_line = None
        self.bytecode_offset = None
        self.instruction = None
        self.arg = None
        self.readable_arg = None
        self.current = False

    # resulted object is (current, python_lineno, bytecode_offset, instruction, arg, constant)
    def to_tuple(self):
        """
        returns information as tuple
        """

        return (self.current, self.py_line, self.bytecode_offset, self.instruction, self.arg, self.readable_arg)


def dis(co, lasti=-1):
    """
    disassembles a code object into tuples
    """

    result = []

    code = co.co_code
    labels = findlabels(code)
    linestarts = dict(findlinestarts(co))
    n = len(code)
    i = 0
    extended_arg = 0
    free = None
    while i < n:
        c = code[i]
        op = ord(c)
        de = DisElement()
        result.append(de)

        if i in linestarts:
            de.python_lineno = linestarts[i]

        de.current = i == lasti
        de.bytecode_offset = i
        de.instruction = opname[op]
        i = i+1
        if op >= HAVE_ARGUMENT:
            oparg = ord(code[i]) + ord(code[i+1])*256 + extended_arg
            extended_arg = 0
            i = i+2
            if op == EXTENDED_ARG:
                extended_arg = oparg*65536L
            de.arg = oparg


            if op in hasconst:
                de.readable_arg = co.co_consts[oparg]
            elif op in hasname:
                de.readable_arg = co.co_names[oparg]
            elif op in hasjrel:
                de.readable_arg = i + oparg
            elif op in haslocal:
                de.readable_arg = co.co_varnames[oparg]
            elif op in hascompare:
                de.readable_arg = cmp_op[oparg]
            elif op in hasfree:
                if free is None:
                    free = co.co_cellvars + co.co_freevars
                de.readable_arg = free[oparg]

    r = [d.to_tuple() for d in result]
    return r


def findlabels(code):
    """
    detect all offsets in a byte code which are jump targets

    return the list of offsets
    """

    labels = []
    n = len(code)
    i = 0
    while i < n:
        c = code[i]
        op = ord(c)
        i = i+1
        if op >= HAVE_ARGUMENT:
            oparg = ord(code[i]) + ord(code[i+1])*256
            i = i+2
            label = -1
            if op in hasjrel:
                label = i+oparg
            elif op in hasjabs:
                label = oparg
            if label >= 0:
                if label not in labels:
                    labels.append(label)
    return labels


def findlinestarts(code):
    """
    find the offsets in a byte code which are start of lines in the source

    generate pairs (offset, lineno) as described in Python/compile.c
    """

    byte_increments = [ord(c) for c in code.co_lnotab[0::2]]
    line_increments = [ord(c) for c in code.co_lnotab[1::2]]

    lastlineno = None
    lineno = code.co_firstlineno
    addr = 0
    for byte_incr, line_incr in zip(byte_increments, line_increments):
        if byte_incr:
            if lineno != lastlineno:
                yield (addr, lineno)
                lastlineno = lineno
            addr += byte_incr
        lineno += line_incr
    if lineno != lastlineno:
        yield (addr, lineno)


def wait_for_connection():
    """
    spinlock at early execution for debugger client to connect
    """

    while not handler.is_client_attached():
        time.sleep(10) # spinlock


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
