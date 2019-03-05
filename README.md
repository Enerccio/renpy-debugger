# Ren'Py debugger

Ren'Py debugger is drop in real time debugger for python code in your [Ren'Py](https://github.com/renpy/renpy) project.

## How to use

1) Copy `0000_debugger.rpy`, `debugger.py` and folder `librpydb` in your project in `game/` folder

2) Launch your project

3) Nothing will happen, but your game is already active and waiting for connection from debugger to actually debug the game

4) Launch your debugger, set up your breakpoints and connect (see section _TUI debugger_)

5) After you are done, remove both files and folder from your `game/` folder and resume your work.

## TUI Debugger

Right now, graphical debugger is work-in-progress, but you can use text user interface debugger. Simply launch it with `python manual_debugger.py` or `python2 manual_debugger.py` if you are under archlinux.

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
bytet - shows bytecode of current frame
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
$ python2 manual_debugger.py
b game/script.rpy:3

OK
connect

Establishing connection
Installed breakpoints set([3]) for source game/script.rpy
Connected!
OK
Stopped (breakpoint) game/script.rpy:3
bt

Backtrace for thread [0]
#0: <game/script.rpy:3> test_call(x)
#1: <game/script.rpy:5> <module>()
#2: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#3: </opt/renpy/renpy/ast.py:896> execute(self)
#4: </opt/renpy/renpy/execution.py:553> run(self, node)
#5: </opt/renpy/renpy/main.py:430> main()
#6: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#7: </opt/renpy/renpy.py:195> main()
#8: </opt/renpy/renpy.py:198> <module>()
OK
locals

#2: x (<type 'int'>)=10
OK
bytet

Bytecode of stack frame #0: <game/script.rpy:3> test_call(x)  
*  0 [LOAD_FAST] (0, x)
3 [PRINT_ITEM]
4 [PRINT_NEWLINE]
5 [LOAD_CONST] (0, None)
8 [RETURN_VALUE]
OK
so

OK
Stopped (stepOut) game/script.rpy:5
bt

Backtrace for thread [0]
#0: <game/script.rpy:5> <module>()
#1: </opt/renpy/renpy/python.py:1929> py_exec_bytecode(bytecode, hide, globals, locals, store)
#2: </opt/renpy/renpy/ast.py:896> execute(self)
#3: </opt/renpy/renpy/execution.py:553> run(self, node)
#4: </opt/renpy/renpy/main.py:430> main()
#5: </opt/renpy/renpy/bootstrap.py:313> bootstrap(renpy_base)
#6: </opt/renpy/renpy.py:195> main()
#7: </opt/renpy/renpy.py:198> <module>()
OK
locals

#2: ADVCharacter (<type 'type'>)=<class 'renpy.character.ADVCharacter'>
#3: ADVSpeaker (<type 'type'>)=<class 'renpy.character.ADVCharacter'>
#4: Action (<type 'type'>)=<class 'renpy.ui.Action'>
...
#526: zoomout (<class 'renpy.curry.Curry'>)=<curry <function OldMoveTransition at 0x7fecaf40b668> (0.5,) {'leave_factory': <curry <function ZoomInOut at 0x7fecaf40b578> (1.0, 0.01) {}>}>
OK

^C
```

## Remaining information

If you see this line in Ren'py console output: `Exception AttributeError: "'NoneType' object has no attribute 'STEP_NO_STEP'" in <function _remove at 0x7fecb9c53578> ignored` do not worry, it is because renpy unloads the module when shutting down, but tracer is still active, so it will crash. There is currently no solution to solve this but it is harmless.
