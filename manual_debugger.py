from __future__ import print_function

import os
import sys
import threading
import socket
import json
import readline
import traceback
import time

from librpydb.debugger import *
from librpydb.baseconf import DEBUGGER_PORT as debugger_port
from librpydb.utils import get_input


renpy_debugger = RenpyDebugger("127.0.0.1", debugger_port)
execution_paused_state = None
execution_threads = []
executed_thread = None
executed_stack_frames = None
executed_stack_frame = None
showing_variables = None


def connected(*args, **kwargs):
    print("Connected!")


def disconnected(*args, **kwargs):
    global execution_paused_state
    print("Disconnected!")
    execution_paused_state = None


def paused(stop_reason, description, exc):
    class IThread(threading.Thread):
        def run(self):
            global execution_paused_state, execution_threads, executed_thread, executed_stack_frames, executed_stack_frame
            execution_paused_state = exc
            execution_threads = exc.get_threads()
            executed_thread = execution_threads[0]
            executed_stack_frames = executed_thread.get_stack_frames()
            executed_stack_frame = executed_stack_frames[0]

    t = IThread()
    t.start()
    print("Paused for %s (%s)" % (stop_reason, description))


def client_error(*args, **kwargs):
    pass


# setting callbacks
renpy_debugger.set_connected_callback(connected)
renpy_debugger.set_disconnected_callback(disconnected)
renpy_debugger.set_client_error_callback(client_error)
renpy_debugger.set_pause_callback(paused)


while True:
    try:
        data = get_input(">>> ")
        print("")

        if data == "xxx":
            print(globals())

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
            # print("bytet - shows bytecode of current frame")
            print("scopes - shows scopes")
            print("v # - displays subfields of variable # or lists variables in scopes")
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
                renpy_debugger.add_breakpoint(Breakpoint(line, file))
                print("OK")
            except BaseException:
                print("Failed to insert breakpoint, check syntax")

        elif data == "lb":
            #####################
            # List breakpoints
            #####################
            for breakpoint in renpy_debugger.breakpoints:
                print("Breakpoint at %s, line %s" % (breakpoint.source, breakpoint.line))
            print("OK")

        elif data.startswith("rb"):
            #######################
            # Remove breakpoints
            #######################
            if data == "rb":
                renpy_debugger.clear_breakpoints()
                print("All breakpoints removed")
            else:
                rest = data[3:]
                if ":" in rest:
                    file, line = rest.split(":")
                    renpy_debugger.remove_breakpoint(Breakpoint(line, file))
                else:
                    renpy_debugger.remove_breakpoint_from_source(rest)
            print("Don't forget to 'sb' to synchronize breakpoints!")
            print("OK")

        elif renpy_debugger.get_state() == DebuggerState.NOT_CONNECTED:
            # no connection commands
            if data == "connect":
                #############################
                # Connect to debugged game
                #############################
                print("Establishing connection")

                try:
                    renpy_debugger.connect()
                except Exception:
                    print("Failed. Is renpy debugged game running?")

                print("OK")

        else:
            # connected
            if data == "sb":
                ############################
                # Synchronize breakpoints
                ############################
                if renpy_debugger.get_state() == DebuggerState.CONNECTED or renpy_debugger.get_state() == DebuggerState.CONNECTING:
                    print("Not connected")
                else:
                    renpy_debugger.sync_breakpoints()
                    print("OK")

            elif data == "threads" and execution_paused_state is not None and execution_paused_state.is_valid():
                #################
                # List threads
                #################
                execution_threads = execution_paused_state.get_threads()

                print("Threads:")
                it = 0
                for renpy_thread in execution_threads:
                    print("Threads #%s: %s" % (str(it), renpy_thread.get_thread_name()))
                    it += 1
                print("OK")

            elif data.startswith("bt") and execution_paused_state is not None and execution_paused_state.is_valid():
                ###################
                # Show backtrace
                ###################
                try:
                    if data == "bt":
                        thread_id = "0"
                    else:
                        thread_id = data[3:]
                except BaseException:
                    print("Failed to display bt, check syntax")

                if int(thread_id) >= len(execution_threads):
                    print("No thread %s available" % thread_id)
                else:
                    print("Backtrace for thread [%s]" % thread_id)
                    executed_thread = execution_threads[int(thread_id)]
                    executed_stack_frames = executed_thread.get_stack_frames()
                    id = 0
                    for st in executed_stack_frames:
                        print("#%s: <%s:%s> %s " % (str(id), st.get_source(), str(st.get_line()), st.get_line_of_code()))
                        id += 1
                print("OK")


#             elif data.startswith("bytet") and state is not None:
                #############################
                # List bytecode for method
                #############################
#                st = state.stacks["0"][state.active_stack]
#                print("Bytecode of stack frame #%s: <%s:%s> %s  " % (st.id, st.source, str(st.line), st.name))
#                i = 0
#                for bytecode in st.sselements:
#                    if i == st.bytepos:
#                        print("* ", end="")
#                        print(bytecode)
#                        i += 1
#                print("OK")


            elif (data == "st" or data.startswith("st ")) and executed_thread is not None and executed_thread.is_valid():
                #######################
                # Switch stack frame
                #######################
                stid = 0
                if data == "st":
                    stid = 0
                else:
                    try:
                        stid = int(data[3:])
                    except BaseException:
                        print("Failed to set active stack frame, check syntax")
                if stid >= len(executed_stack_frames):
                    print("No such stack frame %s" % (str(stid)))
                else:
                    executed_stack_frame = executed_stack_frames[stid]
                    executed_stack_frame.set_active()
                    print("#%s: <%s:%s> %s " % (str(stid), executed_stack_frame.get_source(), str(executed_stack_frame.get_line()), executed_stack_frame.get_line_of_code()))
                print("OK")

            elif data == "scopes" and executed_stack_frame is not None and executed_stack_frame.is_valid():
                ###################
                # Display locals, globas
                ###################

                showing_variables = executed_stack_frame.get_scopes()
                it = 0
                for v in showing_variables:
                    print("#%s: %s (%s) - %s" % (str(it), v.get_name(), v.get_type(), v.get_value()))
                    it += 1
                print("OK")

            elif data.startswith("v "):
                ###############################
                # Display variable structure
                ###############################
                try:
                    var_ref = int(data[2:])
                except BaseException:
                    print("Failed to get variable, check syntax")
                else:
                    if var_ref >= len(showing_variables):
                        print("No such variable %s" % (str(var_ref)))
                    else:
                        showing_variables = list(showing_variables[var_ref].get_components().values())
                        it = 0
                        for v in showing_variables:
                            print("#%s: %s (%s) - %s" % (str(it), v.get_name(), v.get_type(), v.get_value()))
                            it += 1
                        print("OK")

            elif data.startswith("c") and executed_thread is not None and executed_thread.is_valid():
                #######################
                # Continue execution
                #######################
                exct = executed_thread
                executed_thread = None
                exct.continue_execution()
                print("OK")

            elif data.startswith("p") and renpy_debugger.get_state() == DebuggerState.CONNECTED:
                ####################
                # Pause execution
                ####################
                renpy_debugger.pause()
                print("OK")

            elif data == "s" and executed_thread is not None and executed_thread.is_valid():
                ###################
                # Step execution
                ###################
                executed_thread.step()
                print("OK")

            elif data == "si" and executed_thread is not None and executed_thread.is_valid():
                ###################
                # Step into exec
                ###################
                executed_thread.step_in()
                print("OK")

            elif data == "so" and executed_thread is not None and executed_thread.is_valid():
                ##################
                # Step out exec
                ##################
                executed_thread.step_out()
                print("OK")

            elif data == "disconnect" and renpy_debugger.get_state() != DebuggerState.NOT_CONNECTED:
                ###############
                # Disconnect
                ###############
                renpy_debugger.disconnect()
                print("OK")

    except BaseException as e:
        if isinstance(e, KeyboardInterrupt):
            traceback.print_exc()
            break

        print("Oops, something went wrong.")
        traceback.print_exc()
