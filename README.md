# Ren'Py debugger

Ren'Py debugger is drop in real time debugger for python code in your [Ren'Py](https://github.com/renpy/renpy) project.

## How to use

1) Copy `0000_debugger.rpy`, `debugger.py` and folder `librpydb` in your project in `game/` folder

2) Launch your project

3) Nothing will happen, but your game is already active and waiting for connection from debugger to actually debug the game

4) Launch your debugger, set up your breakpoints and connect (see section _TUI debugger_)

5) After you are done, remove both files and folder from your `game/` folder and resume your work.

## TUI Debugger

Right now, graphical debugger is work-in-progress, but you can use text user interface debugger. Simply launch it with `python manual_debugger.py`.

Typing help will list all available commands:

```
connect - connects to debugged renpy game on port 14711
  will automatically sync breakpoints
disconnect - stops debugging, but can still be attached later
b - sets the breakpoint: b game/script.rpy:10
rb - removes breakpoint - arguments can be source, source:line or nothing -> removes all
lb - lists breakpoints
sb - synchronized breakpoints
threads - lists threads, renpy only supports thread 0
bt - shows backtrace of thread
st - st # - switch to stack frame #
locals - shows all local variables
globals - shows all global variables
v # - displays subfields of variable #
c - continue (with the) execution
p - pauses execution wherever it is
s - moves execution by next step
si - moves execution into function call
so - moves execution out of call
```

### Example usage:

```
$ python manual_debugger.py
b game/script.rpy:3

OK
connect
connect

Establishing connection
OK
>>> Paused for breakpoint (game/script.rpy:3)


>>> bt

Backtrace for thread [0]
#0: <game/script.rpy:3> test_call(x)
#1: <game/script.rpy:6> <module>()
#2: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#3: </opt/renpy/renpy/ast.py:896> execute(self)
#4: </opt/renpy/renpy/execution.py:553> run(self, node)
#5: </opt/renpy/renpy/main.py:430> main()
#6: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#7: </opt/renpy/renpy.py:195> main()
#8: </opt/renpy/renpy.py:198> <module>()
OK
>>> s

OK
>>> Paused for step (game/script.rpy:4)


>>> si

OK
>>> Paused for step (game/script.rpy:4)


>>> bt

Backtrace for thread [0]
#0: <game/script.rpy:4> test_call(x)
#1: <game/script.rpy:6> <module>()
#2: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#3: </opt/renpy/renpy/ast.py:896> execute(self)
#4: </opt/renpy/renpy/execution.py:553> run(self, node)
#5: </opt/renpy/renpy/main.py:430> main()
#6: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#7: </opt/renpy/renpy.py:195> main()
#8: </opt/renpy/renpy.py:198> <module>()
OK
>>> si

OK
>>> Disconnected!


>>> connect

Establishing connection
OK
>>> Paused for breakpoint (game/script.rpy:3)


>>> si

OK
>>> Paused for stepIn (/opt/renpy/renpy/log.py:225)


>>> bt

Backtrace for thread [0]
#0: </opt/renpy/renpy/log.py:225> write(self, s)
#1: <game/script.rpy:3> test_call(x)
#2: <game/script.rpy:21> <module>()
#3: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#4: </opt/renpy/renpy/ast.py:896> execute(self)
#5: </opt/renpy/renpy/execution.py:553> run(self, node)
#6: </opt/renpy/renpy/main.py:430> main()
#7: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#8: </opt/renpy/renpy.py:195> main()
#9: </opt/renpy/renpy.py:198> <module>()
OK
>>> so

OK
>>> Paused for stepOut (/opt/renpy/renpy/log.py:223)


>>> bt

Backtrace for thread [0]
#0: </opt/renpy/renpy/log.py:225> write(self, s)
#1: <game/script.rpy:3> test_call(x)
#2: <game/script.rpy:21> <module>()
#3: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#4: </opt/renpy/renpy/ast.py:896> execute(self)
#5: </opt/renpy/renpy/execution.py:553> run(self, node)
#6: </opt/renpy/renpy/main.py:430> main()
#7: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#8: </opt/renpy/renpy.py:195> main()
#9: </opt/renpy/renpy.py:198> <module>()
OK
>>> so

OK
>>> Paused for stepOut (game/script.rpy:4)


>>> bt

Backtrace for thread [0]
#0: <game/script.rpy:4> test_call(x)
#1: <game/script.rpy:21> <module>()
#2: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#3: </opt/renpy/renpy/ast.py:896> execute(self)
#4: </opt/renpy/renpy/execution.py:553> run(self, node)
#5: </opt/renpy/renpy/main.py:430> main()
#6: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#7: </opt/renpy/renpy.py:195> main()
#8: </opt/renpy/renpy.py:198> <module>()
OK
>>> si

OK
>>> Paused for stepIn (game/script.rpy:7)


>>> bt

Backtrace for thread [0]
#0: <game/script.rpy:7> xxx()
#1: <game/script.rpy:4> test_call(x)
#2: <game/script.rpy:21> <module>()
#3: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#4: </opt/renpy/renpy/ast.py:896> execute(self)
#5: </opt/renpy/renpy/execution.py:553> run(self, node)
#6: </opt/renpy/renpy/main.py:430> main()
#7: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#8: </opt/renpy/renpy.py:195> main()
#9: </opt/renpy/renpy.py:198> <module>()
OK
>>> si

OK
>>> Paused for step (game/script.rpy:8)


>>> bt

Backtrace for thread [0]
#0: <game/script.rpy:8> xxx()
#1: <game/script.rpy:4> test_call(x)
#2: <game/script.rpy:21> <module>()
#3: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#4: </opt/renpy/renpy/ast.py:896> execute(self)
#5: </opt/renpy/renpy/execution.py:553> run(self, node)
#6: </opt/renpy/renpy/main.py:430> main()
#7: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#8: </opt/renpy/renpy.py:195> main()
#9: </opt/renpy/renpy.py:198> <module>()
OK
>>> si

OK
>>> Paused for step (game/script.rpy:9)


>>> bt

Backtrace for thread [0]
#0: <game/script.rpy:9> xxx()
#1: <game/script.rpy:4> test_call(x)
#2: <game/script.rpy:21> <module>()
#3: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#4: </opt/renpy/renpy/ast.py:896> execute(self)
#5: </opt/renpy/renpy/execution.py:553> run(self, node)
#6: </opt/renpy/renpy/main.py:430> main()
#7: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#8: </opt/renpy/renpy.py:195> main()
#9: </opt/renpy/renpy.py:198> <module>()
OK
>>> si

OK
>>> Paused for step (game/script.rpy:10)


>>> bt

Backtrace for thread [0]
#0: <game/script.rpy:10> xxx()
#1: <game/script.rpy:4> test_call(x)
#2: <game/script.rpy:21> <module>()
#3: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#4: </opt/renpy/renpy/ast.py:896> execute(self)
#5: </opt/renpy/renpy/execution.py:553> run(self, node)
#6: </opt/renpy/renpy/main.py:430> main()
#7: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#8: </opt/renpy/renpy.py:195> main()
#9: </opt/renpy/renpy.py:198> <module>()
OK
>>> si

OK
>>> Paused for step (game/script.rpy:11)


>>> bt

Backtrace for thread [0]
#0: <game/script.rpy:11> xxx()
#1: <game/script.rpy:4> test_call(x)
#2: <game/script.rpy:21> <module>()
#3: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#4: </opt/renpy/renpy/ast.py:896> execute(self)
#5: </opt/renpy/renpy/execution.py:553> run(self, node)
#6: </opt/renpy/renpy/main.py:430> main()
#7: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#8: </opt/renpy/renpy.py:195> main()
#9: </opt/renpy/renpy.py:198> <module>()
OK
>>> si

OK
>>> Paused for stepIn (game/script.rpy:17)


>>> bt

Backtrace for thread [0]
#0: <game/script.rpy:17> yyy()
#1: <game/script.rpy:11> xxx()
#2: <game/script.rpy:4> test_call(x)
#3: <game/script.rpy:21> <module>()
#4: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#5: </opt/renpy/renpy/ast.py:896> execute(self)
#6: </opt/renpy/renpy/execution.py:553> run(self, node)
#7: </opt/renpy/renpy/main.py:430> main()
#8: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#9: </opt/renpy/renpy.py:195> main()
#10: </opt/renpy/renpy.py:198> <module>()
OK
```

## Remaining information

If you see this line in Ren'py console output: `Exception AttributeError: "'NoneType' object has no attribute 'STEP_NO_STEP'" in <function _remove at 0x7fecb9c53578> ignored` do not worry, it is because renpy unloads the module when shutting down, but tracer is still active, so it will crash. There is currently no solution to solve this but it is harmless.
