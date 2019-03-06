from __future__ import print_function

import os
import sys
import threading
import socket
import json
import readline
import traceback

from librpydb.protocol import DAPMessage
from librpydb.baseconf import DEBUGGER_PORT as debugger_port

class Counter(object):
    def __init__(self):
        self.state = 0

    def get(self):
        s = self.state
        self.state += 1
        return s


rq_counter = Counter()
rq_arguments = {}


class State(object):
    @staticmethod
    def load_state(stage=0, tid=0):
        global state

        if stage == 0:
            state = State()
            DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "threads"}))
        if stage == 1:
            DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "stackTrace", "arguments": {"threadId": tid, "startFrame": 0, "levels": 0}}))

    @staticmethod
    def load_scopes():
        global state

        DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "scopes", "arguments": {"frameId": state.active_stack}}))

    def __init__(self):
        self.threads = []
        self.stacks = {}
        self.active_stack = 0
        self.locs = None
        self.globs = None
        self.vars = {}

    def load_variable(self, vref):
        if vref not in self.vars:
            sq = rq_counter.get()
            rq_arguments[sq] = vref
            DAPMessage.send_text(s, json.dumps({"seq": sq, "command": "variables", "arguments": {"variablesReference": vref}}))
        while vref not in self.vars:
            pass
        if self.vars[vref] is None:
            print("Error retrieving variable %s" % str(vref))
            del self.vars[vref]
            return

    def print_variable(self, vref):
        if vref not in self.vars:
            return

        variables = self.vars[vref]
        for v in variables:
            fmt = "#%s: %s (%s)=%s"
            if len(v["value"]) > 60:
                # move to new line
                "#%s: %s (%s)=\n  %s"
            print(fmt % (str(v["variablesReference"]), str(v["name"]), str(v["type"]), str(v["value"])))


class StackTraceElement(object):
    def __init__(self):
        self.id = None
        self.name = None
        self.source = "<unavailable>"
        self.line = None
        self.bytepos = None
        self.sselements = []


class PrintingDAPMessage(threading.Thread):
    def __init__(self, socket):
        threading.Thread.__init__(self)
        self.daemon = True

        self.socket = socket
        self.start()

    def run(self):
        global in_wait
        global s

        try:
            while True:
                request = DAPMessage.recv_raw(self.socket)
                # print request

                if request is None:
                    print("Disconnected")
                    return

                if request["type"] == "response" and not request["success"]:
                    if int(request["request_seq"]) in rq_arguments:
                        parent_varref = rq_arguments[int(request["request_seq"])]
                        self.vars[vref] = None
                    print(request["type"]["message"], request["type"]["body"]["error"])
                elif request["type"] == "event":
                    if request["event"] == "stopped":
                        print "Stopped (" + request["body"]["reason"] + ")", request["body"]["description"]
                        in_wait = True
                        State.load_state(0)
                elif request["type"] == "response":
                    if request["command"] == "threads":
                        for t in request["body"]["threads"]:
                            state.threads.append((t["id"], t["name"]))
                            State.load_state(1, tid=t["id"])
                    elif request["command"] == "stackTrace":
                        stacks = []
                        for sf in request["body"]["stackFrames"]:
                            st = StackTraceElement()
                            st.id = sf["id"]
                            st.name = sf["name"]
                            st.source = sf["source"]["path"] if sf["source"] is not None else None
                            st.line = sf["line"]
                            st.bytepos = sf["subsourceElement"] if sf["subsourceElement"] is not None else None
                            st.sselements = [x["text"] for x in sf["subsource"]["sources"]] if sf["subsource"] is not None else []
                            stacks.append(st)
                        state.stacks["0"] = stacks
                        state.active_stack = 0
                        state.locs = None
                        state.globs = None
                        state.vars = {}
                        State.load_scopes()
                    elif request["command"] == "scopes":
                        state.locs = request["body"]["scopes"][0]
                        state.globs = request["body"]["scopes"][1]
                        state.vars = {}
                    elif request["command"] == "variables":
                        parent_varref = rq_arguments[int(request["request_seq"])]
                        state.vars[parent_varref] = request["body"]["variables"]


        except BaseException as e:
            # failure while communicating
            traceback.print_exc()

        finally:
            s = None


s = None
in_wait = False
state = None

breakpoints = set()
removed = set()

def mk_breakpoints():
    source_map = {}
    for src, line in breakpoints:
        if src not in source_map:
            source_map[src] = set()
        source_map[src].add(line)

    for src, line in removed:
        if src not in source_map:
            source_map[src] = set()
    removed.clear()

    breakpoint_requests = []
    for source in source_map:
        req = {}
        req["seq"] = rq_counter.get()  # renpy debugger ignores seq anyways, but tries to be correct
        req["command"] = "setBreakpoints"
        args = {}
        req["arguments"] = args
        args["source"] = {"path": source}
        args["breakpoints"] = [{"line": l} for l in source_map[source]]

        display = "Installed breakpoints %s for source %s" % (str(source_map[source]), source)

        breakpoint_requests.append((req, display))

    return breakpoint_requests


while True:
    try:
        data = raw_input("")
        print("")

        # always active commands
        if data == "h" or data == "help":
            #########
            # Help
            #########
            print("Available commands:")
            print("connect - connects to debugged renpy game on port 14711")
            print("  will automatically sync breakpoints")
            print("disconnect - stops debugging, but can still be attached later")
            print("b - sets the breakpoint: b game/script.rpy:10")
            print("rb - removes breakpoint - arguments can be source, source:line or nothing -> removes all")
            print("lb - lists breakpoints")
            print("sb - synchronized breakpoints")
            print("threads - lists threads, renpy only supports thread 0")
            print("bt - shows backtrace of thread")
            print("st - st # - switch to stack frame #")
            print("bytet - shows bytecode of current frame")
            print("locals - shows all local variables")
            print("globals - shows all global variables")
            print("v # - displays subfields of variable #")
            print("c - continue (with the) execution")
            print("p - pauses execution wherever it is")
            print("s - moves execution by next step")
            print("si - moves execution into function call")
            print("so - moves execution out of call")
            print("OK")


        elif data.startswith("b "):
            #######################
            # Install breakpoint
            #######################
            try:
                file, line = data[2:].split(":")
                breakpoints.add((file, int(line)))
                print("OK")
            except BaseException:
                print("Failed to insert breakpoint, check syntax")

        elif data == "lb":
            #####################
            # List breakpoints
            #####################
            for breakpoint_request, display in mk_breakpoints():
                print display
            print("OK")

        elif data.startswith("rb"):
            #######################
            # Remove breakpoints
            #######################
            if data == "rb":
                for bksrc, bkline in breakpoints:
                    removed.add((bksrc, bkline))

                breakpoints.clear()
                print("All breakpoints removed")
            else:
                rest = data[3:]
                if ":" in rest:
                    file, line = rest.split(":")
                    for bksrc, bkline in breakpoints:
                        if bksrc == file and bkline == line:
                            breakpoints.remove((bksrc, bkline))
                            removed.add((bksrc, bkline))
                            print("Removed breakpoint %s:%s" %(str(bksrc), str(bkline)))
                            break
                else:
                    ab = set()
                    for bksrc, bkline in breakpoints:
                        if bksrc == rest:
                            print("Removed breakpoint %s:%s" %(str(bksrc), str(bkline)))
                            removed.add((bksrc, bkline))
                        else:
                            ab.add((bksrc, bkline))
                    breakpoints = ab
            print("Don't forget to 'sb' to synchronize breakpoints!")
            print("OK")

        elif data.startswith("{"):
            #######################
            # Raw request
            #######################
            DAPMessage.send_text(s, data)
            print "OK"

        elif s is None:
            # no connection commands
            if data == "connect":
                #############################
                # Connect to debugged game
                #############################
                print("Establishing connection")

                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect(("127.0.0.1", debugger_port))
                    PrintingDAPMessage(s)
                except:
                    print("Failed. Is renpy debugged game running?")
                    s = None
                    continue

                DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "initialize"}))
                for breakpoint_request, display in mk_breakpoints():
                    DAPMessage.send_text(s, json.dumps(breakpoint_request))
                    print display
                DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "configurationDone"}))
                DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "launch"}))
                print("Connected!")
                print("OK")

        else:
            # connected
            if data == "sb":
                ############################
                # Synchronize breakpoints
                ############################
                for breakpoint_request, display in mk_breakpoints():
                    DAPMessage.send_text(s, json.dumps(breakpoint_request))
                    print display
                print("OK")

            elif data == "threads" and state is not None:
                #################
                # List threads
                #################
                print "Threads:"
                for t in state.threads:
                    print "Threads #%s: %s" % (str(t[0]), t[1])
                print("OK")

            elif data.startswith("bt") and state is not None:
                ###################
                # Show backtrace
                ###################
                try:
                    if data == "bt":
                        thread_id = "0"
                    else:
                        thread_id = data[3:]
                    print("Backtrace for thread [%s]" % thread_id)

                    if thread_id not in state.stacks:
                        print("No thread %s available" % thread_id)
                    else:
                        for st in state.stacks[thread_id]:
                            (print "#%s: <%s:%s> %s " % (st.id, st.source, str(st.line), st.name))
                    print("OK")
                except BaseException:
                    print("Failed to display bt, check syntax")

            elif data.startswith("bytet") and state is not None:
                #############################
                # List bytecode for method
                #############################
                st = state.stacks["0"][state.active_stack]
                print("Bytecode of stack frame #%s: <%s:%s> %s  "  % (st.id, st.source, str(st.line), st.name))
                i = 0
                for bytecode in st.sselements:
                    if i == st.bytepos:
                        print ("* ", end="")
                    print (bytecode)
                    i += 1
                print("OK")

            elif (data == "st" or data.startswith("st ")) and state is not None:
                #######################
                # Switch stack frame
                #######################
                if data == "st":
                    state.active_stack = 0
                    state.locs = None
                    state.globs = None
                    state.vars = {}
                    State.load_scopes()
                else:
                    try:
                        state.active_stack = int(data[3:])
                        if state.active_stack >= len(state.stacks["0"]):
                            print("Invalid stack frame number, set to " + str(len(state.stacks["0"]) - 1))
                            state.active_stack = len(state.stacks["0"]) - 1
                        state.locs = None
                        state.globs = None
                        state.vars = {}
                        State.load_scopes()
                    except BaseException:
                        print("Failed to set active stack frame, check syntax")
                st = state.stacks["0"][state.active_stack]
                print("Set stack to #%s: <%s:%s> %s  " % (st.id, st.source, str(st.line), st.name))
                print("OK")

            elif data == "locals" and state is not None:
                ###################
                # Display locals
                ###################
                state.load_variable(state.locs["variablesReference"])
                state.print_variable(state.locs["variablesReference"])
                print("OK")

            elif data == "globals" and state is not None:
                ####################
                # Display globals
                ####################
                state.load_variable(state.globs["variablesReference"])
                state.print_variable(state.globs["variablesReference"])
                print("OK")

            elif data.startswith("v "):
                ###############################
                # Display variable structure
                ###############################
                try:
                    varRef = int(data[2:])
                except BaseException:
                    print("Failed to get variable, check syntax")
                else:
                    state.load_variable(varRef)
                    state.print_variable(varRef)
                    print("OK")

            elif data.startswith("c") and in_wait:
                #######################
                # Continue execution
                #######################
                state = None
                DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "continue", "arguments": {"threadId": 0}}))
                print("OK")

            elif data.startswith("p") and not in_wait:
                ####################
                # Pause execution
                ####################
                DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "pause", "arguments": {"threadId": 0}}))
                print("OK")

            elif data == "s" and in_wait:
                ###################
                # Step execution
                ###################
                state = None
                DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "next", "arguments": {"threadId": 0}}))
                print("OK")

            elif data == "si" and in_wait:
                ###################
                # Step into exec
                ###################
                state = None
                DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "stepIn", "arguments": {"threadId": 0}}))
                print("OK")

            elif data == "so" and in_wait:
                ##################
                # Step out exec
                ##################
                state = None
                DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "stepOut", "arguments": {"threadId": 0}}))
                print("OK")

            elif data == "disconnect":
                ###############
                # Disconnect
                ###############
                DAPMessage.send_text(s, json.dumps({"seq": rq_counter.get(), "command": "disconnect", "arguments": {"threadId": 0}}))
                print("OK")

    except BaseException as e:
        if isinstance(e, KeyboardInterrupt):
            break

        print("Oops, something went wrong.")
        traceback.print_exc()
