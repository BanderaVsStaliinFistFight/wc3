#!/usr/bin/env python3
"""A small JASS interpreter with a mock game world, used to smoke-test the
map script without running Warcraft III.

It parses common.j, Blizzard.j and war3map.j, runs config() and main(), and
then advances game time while scripted "player actions" happen (picking
heroes, killing creeps, capturing outposts, finishing quests ...). Runtime
errors that the game would silently swallow -- reading an uninitialised
variable, integer division by zero, too many operations in one thread,
ExecuteFunc on a missing function -- are reported as failures.

Usage:
    python3 tools/jass_sim.py common.j Blizzard.j war3map.j [--scenario NAME]

common.j and Blizzard.j are Blizzard's files and are not part of this
repository; extract them from your game (Scripts\\common.j, Scripts\\Blizzard.j).
"""

import heapq
import math
import random
import re
import sys

# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

KEYWORDS = {
    'function', 'endfunction', 'takes', 'returns', 'nothing', 'native', 'constant',
    'globals', 'endglobals', 'local', 'set', 'call', 'if', 'then', 'elseif', 'else',
    'endif', 'loop', 'endloop', 'exitwhen', 'return', 'and', 'or', 'not', 'type',
    'extends', 'array', 'true', 'false', 'null', 'debug',
}

TOKEN_RE = re.compile(r'''
    (?P<ws>[ \t]+)
  | (?P<comment>//[^\n]*)
  | (?P<nl>\r?\n)
  | (?P<real>\d+\.\d*|\.\d+)
  | (?P<hex>0[xX][0-9a-fA-F]+|\$[0-9a-fA-F]+)
  | (?P<int>\d+)
  | (?P<raw>'(?:\\.|[^'\\])*')
  | (?P<str>"(?:\\.|[^"\\])*")
  | (?P<id>[A-Za-z][A-Za-z0-9_]*)
  | (?P<op>==|!=|<=|>=|[-+*/=<>()\[\],])
''', re.X)


class JassError(Exception):
    pass


def lex(src, filename):
    toks = []
    pos = 0
    line = 1
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise JassError('%s:%d: bad character %r' % (filename, line, src[pos]))
        kind = m.lastgroup
        text = m.group(kind)
        if kind == 'nl':
            toks.append(('nl', None, line))
            line += 1
        elif kind in ('ws', 'comment'):
            pass
        elif kind == 'real':
            toks.append(('real', float(text), line))
        elif kind == 'hex':
            toks.append(('int', int(text.lstrip('$').replace('0x', '').replace('0X', ''), 16), line))
        elif kind == 'int':
            v = int(text, 8) if len(text) > 1 and text.startswith('0') else int(text)
            toks.append(('int', v, line))
        elif kind == 'raw':
            body = bytes(text[1:-1], 'latin-1').decode('unicode_escape').encode('latin-1')
            v = 0
            for b in body:
                v = v * 256 + b
            toks.append(('int', v, line))
        elif kind == 'str':
            body = text[1:-1]
            body = re.sub(r'\\(.)', lambda mm: {'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f'}.get(mm.group(1), mm.group(1)), body)
            toks.append(('str', body, line))
        elif kind == 'id':
            toks.append(('kw' if text in KEYWORDS else 'id', text, line))
        else:
            toks.append(('op', text, line))
        pos = m.end()
    toks.append(('nl', None, line))
    toks.append(('eof', None, line))
    return toks


# ---------------------------------------------------------------------------
# Parser -> tuples
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, toks, filename):
        self.t = toks
        self.i = 0
        self.f = filename

    def peek(self, k=0):
        return self.t[self.i + k]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def err(self, msg):
        raise JassError('%s:%d: %s' % (self.f, self.peek()[2], msg))

    def accept(self, kind, val=None):
        tok = self.peek()
        if tok[0] == kind and (val is None or tok[1] == val):
            self.i += 1
            return tok
        return None

    def expect(self, kind, val=None):
        tok = self.accept(kind, val)
        if not tok:
            self.err('expected %s %s, got %r' % (kind, val or '', self.peek()[1]))
        return tok

    def skip_nl(self):
        while self.peek()[0] == 'nl':
            self.i += 1

    def end_line(self):
        if self.peek()[0] not in ('nl', 'eof'):
            self.err('expected end of line, got %r' % (self.peek()[1],))
        self.skip_nl()

    def parse_file(self, prog):
        self.skip_nl()
        while self.peek()[0] != 'eof':
            tok = self.peek()
            if tok == ('kw', 'type', tok[2]):
                self.next()
                name = self.expect('id')[1]
                self.expect('kw', 'extends')
                self.next()
                prog.types[name] = True
                self.end_line()
            elif tok[1] == 'globals':
                self.next()
                self.end_line()
                while not self.accept('kw', 'endglobals'):
                    prog.globals.append(self.var_decl(True))
                self.end_line()
            elif tok[1] in ('native', 'constant') and (tok[1] == 'native' or self.peek(1)[1] == 'native'):
                if tok[1] == 'constant':
                    self.next()
                self.next()
                name, params, ret = self.signature()
                prog.natives[name] = (params, ret)
                self.end_line()
            elif tok[1] in ('function', 'constant'):
                if tok[1] == 'constant':
                    self.next()
                self.expect('kw', 'function')
                line = self.peek()[2]
                name, params, ret = self.signature()
                self.end_line()
                body = self.block(('endfunction',))
                self.expect('kw', 'endfunction')
                self.end_line()
                if name in prog.functions:
                    raise JassError('%s:%d: function %s redefined' % (self.f, line, name))
                prog.functions[name] = (params, ret, body, self.f, line)
            else:
                self.err('unexpected %r at top level' % (tok[1],))

    def signature(self):
        name = self.expect('id')[1]
        self.expect('kw', 'takes')
        params = []
        if not self.accept('kw', 'nothing'):
            while True:
                ptype = self.next()[1]
                pname = self.expect('id')[1]
                params.append((ptype, pname))
                if not self.accept('op', ','):
                    break
        self.expect('kw', 'returns')
        ret = self.next()[1]
        return name, params, ret

    def var_decl(self, is_global):
        line = self.peek()[2]
        const = bool(self.accept('kw', 'constant'))
        vtype = self.next()[1]
        is_array = bool(self.accept('kw', 'array'))
        name = self.expect('id')[1]
        init = None
        if self.accept('op', '='):
            init = self.expr()
        self.end_line()
        return ('var', vtype, is_array, name, init, const, line)

    def block(self, enders):
        stmts = []
        while not (self.peek()[0] == 'kw' and self.peek()[1] in enders):
            stmts.append(self.statement())
        return stmts

    def statement(self):
        tok = self.peek()
        line = tok[2]
        kw = tok[1] if tok[0] == 'kw' else None
        if kw == 'debug':
            self.next()
            tok = self.peek()
            kw = tok[1]
        if kw == 'local':
            self.next()
            d = self.var_decl(False)
            return ('local',) + d[1:]
        if kw == 'set':
            self.next()
            name = self.expect('id')[1]
            idx = None
            if self.accept('op', '['):
                idx = self.expr()
                self.expect('op', ']')
            self.expect('op', '=')
            val = self.expr()
            self.end_line()
            return ('set', name, idx, val, line)
        if kw == 'call':
            self.next()
            e = self.call_expr()
            self.end_line()
            return ('callstmt', e, line)
        if kw == 'if':
            self.next()
            branches = []
            cond = self.expr()
            self.expect('kw', 'then')
            self.end_line()
            body = self.block(('elseif', 'else', 'endif'))
            branches.append((cond, body))
            els = None
            while True:
                if self.accept('kw', 'elseif'):
                    cond = self.expr()
                    self.expect('kw', 'then')
                    self.end_line()
                    branches.append((cond, self.block(('elseif', 'else', 'endif'))))
                elif self.accept('kw', 'else'):
                    self.end_line()
                    els = self.block(('endif',))
                else:
                    break
            self.expect('kw', 'endif')
            self.end_line()
            return ('if', branches, els, line)
        if kw == 'loop':
            self.next()
            self.end_line()
            body = self.block(('endloop',))
            self.expect('kw', 'endloop')
            self.end_line()
            return ('loop', body, line)
        if kw == 'exitwhen':
            self.next()
            e = self.expr()
            self.end_line()
            return ('exitwhen', e, line)
        if kw == 'return':
            self.next()
            e = None
            if self.peek()[0] != 'nl':
                e = self.expr()
            self.end_line()
            return ('return', e, line)
        self.err('unexpected %r' % (tok[1],))

    def call_expr(self):
        name = self.expect('id')[1]
        line = self.peek()[2]
        self.expect('op', '(')
        args = []
        if not self.accept('op', ')'):
            while True:
                args.append(self.expr())
                if self.accept('op', ')'):
                    break
                self.expect('op', ',')
        return ('call', name, args, line)

    # precedence climbing
    def expr(self):
        return self.or_expr()

    def or_expr(self):
        e = self.and_expr()
        while self.accept('kw', 'or'):
            e = ('or', e, self.and_expr())
        return e

    def and_expr(self):
        e = self.cmp_expr()
        while self.accept('kw', 'and'):
            e = ('and', e, self.cmp_expr())
        return e

    def cmp_expr(self):
        e = self.add_expr()
        while self.peek()[0] == 'op' and self.peek()[1] in ('==', '!=', '<', '>', '<=', '>='):
            op = self.next()[1]
            e = ('bin', op, e, self.add_expr())
        return e

    def add_expr(self):
        e = self.mul_expr()
        while self.peek()[0] == 'op' and self.peek()[1] in ('+', '-'):
            op = self.next()[1]
            e = ('bin', op, e, self.mul_expr())
        return e

    def mul_expr(self):
        e = self.unary()
        while self.peek()[0] == 'op' and self.peek()[1] in ('*', '/'):
            op = self.next()[1]
            e = ('bin', op, e, self.unary())
        return e

    def unary(self):
        if self.accept('op', '-'):
            return ('neg', self.unary())
        if self.accept('op', '+'):
            return self.unary()
        if self.accept('kw', 'not'):
            return ('not', self.unary())
        return self.primary()

    def primary(self):
        tok = self.peek()
        if tok[0] == 'int':
            self.next()
            return ('lit', tok[1])
        if tok[0] == 'real':
            self.next()
            return ('lit', tok[1])
        if tok[0] == 'str':
            self.next()
            return ('lit', tok[1])
        if tok[0] == 'kw' and tok[1] in ('true', 'false'):
            self.next()
            return ('lit', tok[1] == 'true')
        if tok[0] == 'kw' and tok[1] == 'null':
            self.next()
            return ('lit', None)
        if tok[0] == 'kw' and tok[1] == 'function':
            self.next()
            return ('code', self.expect('id')[1], tok[2])
        if self.accept('op', '('):
            e = self.expr()
            self.expect('op', ')')
            return e
        if tok[0] == 'id':
            if self.peek(1) == ('op', '(', self.peek(1)[2]):
                return self.call_expr()
            self.next()
            if self.accept('op', '['):
                idx = self.expr()
                self.expect('op', ']')
                return ('index', tok[1], idx, tok[2])
            return ('var', tok[1], tok[2])
        self.err('unexpected %r in expression' % (tok[1],))


class Program:
    def __init__(self):
        self.types = {}
        self.globals = []
        self.natives = {}
        self.functions = {}


# ---------------------------------------------------------------------------
# Runtime values
# ---------------------------------------------------------------------------

UNINIT = object()


class Handle:
    _next = 1

    def __init__(self, kind):
        self.kind = kind
        self.hid = Handle._next
        Handle._next += 1

    def __repr__(self):
        return '<%s %d>' % (self.kind, self.hid)


class Code:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return isinstance(other, Code) and other.name == self.name

    def __hash__(self):
        return hash(self.name)


def fourcc(v):
    try:
        return v.to_bytes(4, 'big').decode('latin-1')
    except Exception:
        return str(v)


def to_i32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def default_for(t):
    if t == 'integer':
        return 0
    if t == 'real':
        return 0.0
    if t == 'boolean':
        return False
    if t == 'string':
        return None
    return None


class ExitLoop(Exception):
    pass


class Return(Exception):
    def __init__(self, value):
        self.value = value


class ThreadDied(Exception):
    pass


# ---------------------------------------------------------------------------
# Interpreter
# ---------------------------------------------------------------------------

OP_LIMIT = 300000


class Interp:
    def __init__(self, prog, world):
        self.p = prog
        self.w = world
        world.vm = self
        self.g = {}
        self.gtypes = {}
        self.errors = []
        self.ops = 0
        self.thread_name = None
        self.call_depth = 0
        self.stack = []

    def report(self, msg):
        where = ' > '.join(self.stack[-4:])
        self.errors.append('[t=%.1f %s] %s (in %s)' % (self.w.time, self.thread_name, msg, where))
        raise ThreadDied(msg)

    def init_globals(self):
        self.thread_name = 'globals'
        self.ops = 0
        for (_, vtype, is_array, name, init, const, line) in self.p.globals:
            self.gtypes[name] = vtype
            if is_array:
                self.g[name] = {'__array__': vtype}
            elif init is not None:
                self.g[name] = self.coerce(vtype, self.eval(init, {}))
            else:
                self.g[name] = UNINIT

    def coerce(self, t, v):
        if t == 'real' and isinstance(v, int) and not isinstance(v, bool):
            return float(v)
        return v

    # threads ------------------------------------------------------------

    def run(self, name, args=(), thread=None):
        """Run a function as a new thread; errors kill only this thread."""
        saved = (self.ops, self.thread_name, self.call_depth, self.stack)
        self.ops = 0
        self.call_depth = 0
        self.stack = []
        self.thread_name = thread or name
        try:
            return self.call(name, list(args))
        except ThreadDied:
            return None
        finally:
            self.ops, self.thread_name, self.call_depth, self.stack = saved

    def call(self, name, args):
        if name in self.p.functions:
            params, ret, body, fname, line = self.p.functions[name]
            if len(args) != len(params):
                self.report('%s called with %d args, expects %d' % (name, len(args), len(params)))
            hook = getattr(self.w, 'f_' + name, None)
            if hook is not None:
                hook(*args)
            env = {}
            for (ptype, pname), v in zip(params, args):
                env[pname] = self.coerce(ptype, v)
                env['__type__' + pname] = ptype
            self.call_depth += 1
            self.stack.append(name)
            if self.call_depth > 400:
                self.report('call depth exceeded in %s' % name)
            try:
                self.exec_block(body, env)
            except Return as r:
                self.call_depth -= 1
                self.stack.pop()
                return self.coerce(ret, r.value)
            self.call_depth -= 1
            self.stack.pop()
            if ret != 'nothing':
                self.report('function %s fell off the end without returning' % name)
            return None
        if name in self.p.natives:
            fn = getattr(self.w, 'n_' + name, None)
            if fn is not None:
                return fn(*args)
            ret = self.p.natives[name][1]
            return self.w.default_native(name, ret, args)
        self.report('call to undefined function %s' % name)

    # statements --------------------------------------------------------

    def tick(self, n=1):
        self.ops += n
        if self.ops > OP_LIMIT:
            self.report('operation limit exceeded')

    def exec_block(self, stmts, env):
        for s in stmts:
            self.tick()
            k = s[0]
            if k == 'set':
                _, name, idx, val, line = s
                v = self.eval(val, env)
                if idx is None:
                    if name in env:
                        env[name] = self.coerce(env['__type__' + name], v) if ('__type__' + name) in env else v
                    elif name in self.g:
                        self.g[name] = self.coerce(self.gtypes[name], v)
                    else:
                        self.report('line %d: set of unknown variable %s' % (line, name))
                else:
                    i = self.eval(idx, env)
                    arr = env.get(name) if name in env else self.g.get(name)
                    if not isinstance(arr, dict):
                        self.report('line %d: %s is not an array' % (line, name))
                    if not (0 <= i < 8192):
                        self.report('line %d: array index %d out of range for %s' % (line, i, name))
                    arr[i] = self.coerce(arr['__array__'], v)
            elif k == 'callstmt':
                self.eval(s[1], env)
            elif k == 'local':
                _, vtype, is_array, name, init, const, line = s
                env['__type__' + name] = vtype
                if is_array:
                    env[name] = {'__array__': vtype}
                elif init is not None:
                    env[name] = self.coerce(vtype, self.eval(init, env))
                else:
                    env[name] = UNINIT
            elif k == 'if':
                _, branches, els, line = s
                done = False
                for cond, body in branches:
                    c = self.eval(cond, env)
                    if not isinstance(c, bool):
                        self.report('line %d: if condition is not boolean (%r)' % (line, c))
                    if c:
                        self.exec_block(body, env)
                        done = True
                        break
                if not done and els is not None:
                    self.exec_block(els, env)
            elif k == 'loop':
                try:
                    while True:
                        self.exec_block(s[1], env)
                except ExitLoop:
                    pass
            elif k == 'exitwhen':
                c = self.eval(s[1], env)
                if not isinstance(c, bool):
                    self.report('line %d: exitwhen condition is not boolean' % s[2])
                if c:
                    raise ExitLoop()
            elif k == 'return':
                raise Return(None if s[1] is None else self.eval(s[1], env))

    # expressions -------------------------------------------------------

    def lookup(self, name, env, line):
        if name in env:
            v = env[name]
        elif name in self.g:
            v = self.g[name]
        else:
            self.report('line %d: unknown variable %s' % (line, name))
        if v is UNINIT:
            self.report('line %d: read of uninitialised variable %s' % (line, name))
        return v

    def eval(self, e, env):
        self.tick()
        k = e[0]
        if k == 'lit':
            return e[1]
        if k == 'var':
            v = self.lookup(e[1], env, e[2])
            if isinstance(v, dict):
                self.report('line %d: array %s used without index' % (e[2], e[1]))
            return v
        if k == 'index':
            arr = self.lookup(e[1], env, e[3])
            i = self.eval(e[2], env)
            if not isinstance(arr, dict):
                self.report('line %d: %s is not an array' % (e[3], e[1]))
            if not isinstance(i, int) or not (0 <= i < 8192):
                self.report('line %d: array index %r out of range for %s' % (e[3], i, e[1]))
            return arr.get(i, default_for(arr['__array__']))
        if k == 'call':
            _, name, args, line = e
            vals = [self.eval(a, env) for a in args]
            return self.call(name, vals)
        if k == 'code':
            if e[1] not in self.p.functions:
                self.report('line %d: function reference to unknown %s' % (e[2], e[1]))
            return Code(e[1])
        if k == 'neg':
            v = self.eval(e[1], env)
            return to_i32(-v) if isinstance(v, int) else -v
        if k == 'not':
            v = self.eval(e[1], env)
            if not isinstance(v, bool):
                self.report('not applied to a non-boolean')
            return not v
        if k == 'and':
            return bool(self.eval(e[1], env)) and bool(self.eval(e[2], env))
        if k == 'or':
            return bool(self.eval(e[1], env)) or bool(self.eval(e[2], env))
        if k == 'bin':
            op = e[1]
            a = self.eval(e[2], env)
            b = self.eval(e[3], env)
            if op == '+':
                if isinstance(a, str) or isinstance(b, str) or (a is None and b is None):
                    return (a or '') + (b or '')
                if isinstance(a, float) or isinstance(b, float):
                    return float(a) + float(b)
                return to_i32(a + b)
            if op == '-':
                if isinstance(a, float) or isinstance(b, float):
                    return float(a) - float(b)
                return to_i32(a - b)
            if op == '*':
                if isinstance(a, float) or isinstance(b, float):
                    return float(a) * float(b)
                return to_i32(a * b)
            if op == '/':
                if isinstance(a, float) or isinstance(b, float):
                    if b == 0:
                        self.report('real division by zero')
                    return float(a) / float(b)
                if b == 0:
                    self.report('integer division by zero')
                q = abs(a) // abs(b)
                return to_i32(q if (a >= 0) == (b >= 0) else -q)
            if op == '==':
                return self.equal(a, b)
            if op == '!=':
                return not self.equal(a, b)
            if a is None or b is None:
                self.report('comparison with null')
            if op == '<':
                return a < b
            if op == '>':
                return a > b
            if op == '<=':
                return a <= b
            if op == '>=':
                return a >= b
        raise JassError('bad expression %r' % (e,))

    @staticmethod
    def equal(a, b):
        if isinstance(a, float) or isinstance(b, float):
            if a is None or b is None:
                return False
            return abs(float(a) - float(b)) < 1e-9
        if isinstance(a, str) and b is None:
            return False
        return a == b


# ---------------------------------------------------------------------------
# Mock game world
# ---------------------------------------------------------------------------

STRUCTURES = {
    'hcas', 'htow', 'hkee', 'ngol', 'nfoh', 'ngme', 'nmrk', 'nmer', 'hgtw', 'hatw', 'hctw',
    'hhou', 'hbar', 'uzg1', 'uzig', 'unp2', 'unpl', 'ugrv', 'usep', 'halt',
}
LEVELS = {}
LIFE = {'hcas': 2500, 'unp2': 2000, 'Uktl': 3500}


class Unit(Handle):
    def __init__(self, world, owner, uid, x, y):
        super().__init__('unit')
        self.owner = owner
        self.uid = uid
        self.x = x
        self.y = y
        self.data = 0
        self.max_life = float(LIFE.get(fourcc(uid), 500))
        self.life = self.max_life
        self.hero_level = 1
        self.items = [None] * 6
        self.order = 0
        self.xp = 0

    @property
    def alive(self):
        return self.life > 0.405

    @property
    def is_hero(self):
        return fourcc(self.uid)[0].isupper()

    @property
    def is_structure(self):
        return fourcc(self.uid) in STRUCTURES


class Item(Handle):
    def __init__(self, iid, x, y):
        super().__init__('item')
        self.iid = iid
        self.x = x
        self.y = y


class Timer(Handle):
    def __init__(self):
        super().__init__('timer')
        self.due = None
        self.period = 0.0
        self.periodic = False
        self.func = None
        self.gen = 0


class Trigger(Handle):
    def __init__(self):
        super().__init__('trigger')
        self.actions = []
        self.conditions = []
        self.enabled = True


class World:
    def __init__(self, users, seed=1):
        self.time = 0.0
        self.vm = None
        self.rng = random.Random(seed)
        self.users = users
        self.converted = {}
        self.players = {}
        self.units = []
        self.items = []
        self.timers = []
        self.timer_seq = 0
        self.event_triggers = {}
        self.dialog_triggers = []
        self.leave_triggers = []
        self.chat_triggers = []
        self.messages = []
        self.ctx = []
        self.groups = {}
        self.victory = set()
        self.defeat = set()
        self.dialog_buttons = {}
        self.texttags = 0
        self.stock = {}
        self.disabled = set()

    # helpers ------------------------------------------------------------

    def conv(self, kind, v):
        key = (kind, v)
        if key not in self.converted:
            h = Handle(kind)
            h.value = v
            self.converted[key] = h
        return self.converted[key]

    def default_native(self, name, ret, args):
        if name.startswith('Convert'):
            return self.conv(name[7:], args[0])
        if ret == 'nothing':
            return None
        if ret == 'integer':
            return 0
        if ret == 'real':
            return 0.0
        if ret == 'boolean':
            return False
        if ret == 'string':
            return ''
        return Handle(ret)

    def ctx_get(self, key):
        for c in reversed(self.ctx):
            if key in c:
                return c[key]
        return None

    def fire(self, trigger, ctx):
        if not trigger.enabled:
            return
        self.ctx.append(ctx)
        try:
            ok = True
            for cond in trigger.conditions:
                r = self.vm.run(cond.name, thread='condition ' + cond.name)
                if not r:
                    ok = False
            if ok:
                for act in trigger.actions:
                    self.vm.run(act.name, thread='action ' + act.name)
        finally:
            self.ctx.pop()

    def player_id(self, p):
        for i, h in self.players.items():
            if h is p:
                return i
        return -1

    def global_handle(self, name):
        return self.vm.g[name]

    # players ------------------------------------------------------------

    def n_Player(self, i):
        if i not in self.players:
            h = Handle('player')
            h.pid = i
            h.state = {}
            self.players[i] = h
        return self.players[i]

    # Reforged (1.29+) player layout: 24 player slots, neutrals at 24..27
    def n_GetBJMaxPlayers(self):
        return 24

    def n_GetBJMaxPlayerSlots(self):
        return 28

    def n_GetBJPlayerNeutralVictim(self):
        return 25

    def n_GetBJPlayerNeutralExtra(self):
        return 26

    def n_GetPlayerNeutralPassive(self):
        return 27

    def n_GetPlayerNeutralAggressive(self):
        return 24

    def n_GetPlayerId(self, p):
        return p.pid if p is not None else -1

    def n_GetPlayerSlotState(self, p):
        playing = p.pid in self.users or p.pid in (4, 5)
        return self.conv('PlayerSlotState', 1 if playing else 0)

    def n_GetPlayerController(self, p):
        if p.pid in self.users:
            return self.conv('MapControl', 0)
        if p.pid in (4, 5):
            return self.conv('MapControl', 1)
        if p.pid >= 12:
            return self.conv('MapControl', 3)
        return self.conv('MapControl', 0)

    def n_GetPlayerName(self, p):
        return 'Player%d' % p.pid

    def n_GetLocalPlayer(self):
        return self.n_Player(0)

    def n_GetPlayerState(self, p, state):
        return p.state.get(state.value, 0)

    def n_SetPlayerState(self, p, state, v):
        p.state[state.value] = v

    def n_GetPlayerRace(self, p):
        return self.conv('Race', 1)

    # units --------------------------------------------------------------

    def n_CreateUnit(self, p, uid, x, y, face):
        u = Unit(self, p, uid, x, y)
        self.units.append(u)
        return u

    def n_GetUnitTypeId(self, u):
        return u.uid if u else 0

    def n_GetOwningPlayer(self, u):
        return u.owner if u else None

    def n_GetUnitX(self, u):
        return u.x if u else 0.0

    def n_GetUnitY(self, u):
        return u.y if u else 0.0

    def n_SetUnitUserData(self, u, v):
        if u:
            u.data = v

    def n_GetUnitUserData(self, u):
        return u.data if u else 0

    def n_GetWidgetLife(self, u):
        return u.life if u else 0.0

    def n_SetWidgetLife(self, u, v):
        if u:
            u.life = min(v, u.max_life)

    def n_GetUnitState(self, u, s):
        if u is None:
            return 0.0
        if s is self.global_handle('UNIT_STATE_MAX_LIFE'):
            return u.max_life
        if s is self.global_handle('UNIT_STATE_LIFE'):
            return u.life
        return 0.0

    def n_IsUnitType(self, u, t):
        if u is None:
            return False
        if t is self.global_handle('UNIT_TYPE_HERO'):
            return u.is_hero
        if t is self.global_handle('UNIT_TYPE_STRUCTURE'):
            return u.is_structure
        if t is self.global_handle('UNIT_TYPE_DEAD'):
            return not u.alive
        return False

    def n_GetUnitLevel(self, u):
        return u.hero_level if u and u.is_hero else 3

    def n_GetHeroLevel(self, u):
        return u.hero_level if u else 0

    def n_SetHeroLevel(self, u, lvl, eye):
        u.hero_level = lvl

    def n_AddHeroXP(self, u, xp, eye):
        if xp < 0:
            self.vm.report('negative XP')
        u.xp += xp

    def n_ReviveHero(self, u, x, y, eye):
        if u.alive:
            self.vm.report('ReviveHero on a living hero')
        u.life = u.max_life
        u.x, u.y = x, y
        return True

    def n_KillUnit(self, u):
        self.kill(u, None)

    def n_RemoveUnit(self, u):
        if u in self.units:
            self.units.remove(u)

    def n_GetUnitCurrentOrder(self, u):
        return u.order if u else 0

    def n_IssuePointOrder(self, u, order, x, y):
        if u:
            u.order = 851983
            u.target = (x, y)
        return True

    def n_IssueTargetOrder(self, u, order, t):
        return True

    def n_IssueImmediateOrder(self, u, order):
        return True

    def n_UnitInventorySize(self, u):
        return 6 if u and u.is_hero else 0

    def n_UnitItemInSlot(self, u, slot):
        if u is None or not (0 <= slot < 6):
            return None
        return u.items[slot]

    def n_UnitAddItemById(self, u, iid):
        it = Item(iid, u.x, u.y)
        for i in range(6):
            if u.items[i] is None:
                u.items[i] = it
                return it
        self.items.append(it)
        return it

    def n_GetItemTypeId(self, it):
        return it.iid if it else 0

    def n_CreateItem(self, iid, x, y):
        if iid == 0:
            self.vm.report('CreateItem with item id 0')
        it = Item(iid, x, y)
        self.items.append(it)
        return it

    def n_RemoveItem(self, it):
        for u in self.units:
            for i in range(6):
                if u.items[i] is it:
                    u.items[i] = None
        if it in self.items:
            self.items.remove(it)

    def n_ChooseRandomItemEx(self, kind, level):
        return 0x72617463  # 'ratc'

    def n_GetHeroStr(self, u, bonus):
        return 20

    def n_GetHeroInt(self, u, bonus):
        return 20

    def n_SetHeroStr(self, u, v, perm):
        u.max_life = 100.0 + 25.0 * v

    def n_AddItemToStock(self, u, iid, cur, mx):
        self.stock.setdefault(u.hid, []).append(fourcc(iid))

    # groups -------------------------------------------------------------

    def n_CreateGroup(self):
        g = Handle('group')
        self.groups[g.hid] = []
        return g

    def n_DestroyGroup(self, g):
        self.groups.pop(g.hid, None)
        g.destroyed = True

    def _grp(self, g):
        if g is None:
            return []
        if getattr(g, 'destroyed', False):
            self.vm.report('use of destroyed group')
        return self.groups.setdefault(g.hid, [])

    def n_GroupAddUnit(self, g, u):
        lst = self._grp(g)
        if u is not None and u not in lst:
            lst.append(u)

    def n_GroupRemoveUnit(self, g, u):
        lst = self._grp(g)
        if u in lst:
            lst.remove(u)

    def n_GroupClear(self, g):
        self._grp(g).clear()

    def n_FirstOfGroup(self, g):
        lst = [u for u in self._grp(g) if u in self.units]
        self.groups[g.hid] = lst
        return lst[0] if lst else None

    def n_GroupEnumUnitsInRange(self, g, x, y, r, filt):
        lst = self._grp(g)
        lst.clear()
        for u in self.units:
            if math.hypot(u.x - x, u.y - y) <= r:
                lst.append(u)

    def n_GroupEnumUnitsOfType(self, g, name, filt):
        self._grp(g).clear()

    def n_GroupEnumUnitsOfPlayer(self, g, p, filt):
        lst = self._grp(g)
        lst.clear()
        lst.extend(u for u in self.units if u.owner is p)

    def n_ForGroup(self, g, code):
        for u in list(self._grp(g)):
            self.ctx.append({'enum_unit': u})
            try:
                self.vm.call(code.name, [])
            finally:
                self.ctx.pop()

    def n_GetEnumUnit(self):
        return self.ctx_get('enum_unit')

    def n_ForForce(self, f, code):
        for pid in sorted(getattr(f, 'members', set())):
            self.ctx.append({'enum_player': self.n_Player(pid)})
            try:
                self.vm.call(code.name, [])
            finally:
                self.ctx.pop()

    def n_CreateForce(self):
        f = Handle('force')
        f.members = set()
        return f

    def n_ForceAddPlayer(self, f, p):
        f.members.add(p.pid)

    def n_ForceEnumPlayers(self, f, filt):
        f.members = set(range(28))

    def n_ForceEnumAllies(self, f, p, filt):
        f.members = set(self.users)

    def n_IsPlayerInForce(self, p, f):
        return p.pid in getattr(f, 'members', set())

    def n_GetEnumPlayer(self):
        return self.ctx_get('enum_player')

    # timers -------------------------------------------------------------

    def n_CreateTimer(self):
        return Timer()

    def n_TimerStart(self, t, timeout, periodic, func):
        t.gen += 1
        t.period = timeout
        t.periodic = periodic
        t.func = func
        t.due = self.time + max(timeout, 0.0)
        self.timer_seq += 1
        heapq.heappush(self.timers, (t.due, self.timer_seq, t, t.gen))

    def n_PauseTimer(self, t):
        t.gen += 1
        t.due = None

    def n_DestroyTimer(self, t):
        t.gen += 1
        t.due = None

    def n_TimerGetRemaining(self, t):
        return max(0.0, t.due - self.time) if t and t.due is not None else 0.0

    def n_TimerGetElapsed(self, t):
        return 0.0

    def n_GetExpiredTimer(self):
        return self.ctx_get('timer')

    # triggers -----------------------------------------------------------

    def n_CreateTrigger(self):
        return Trigger()

    def n_TriggerAddAction(self, t, code):
        t.actions.append(code)
        return Handle('triggeraction')

    def n_Condition(self, code):
        h = Handle('conditionfunc')
        h.code = code
        return h

    def n_Filter(self, code):
        h = Handle('filterfunc')
        h.code = code
        return h

    def n_TriggerAddCondition(self, t, cond):
        if cond is not None:
            t.conditions.append(cond.code)
        return Handle('triggercondition')

    def n_DisableTrigger(self, t):
        if t is None:
            self.vm.report('DisableTrigger(null)')
        t.enabled = False
        self.disabled.add(t.hid)

    def n_EnableTrigger(self, t):
        t.enabled = True

    def n_TriggerRegisterPlayerUnitEvent(self, t, p, ev, filt):
        self.event_triggers.setdefault((ev.value, p.pid), []).append(t)
        return Handle('event')

    def n_TriggerRegisterDialogEvent(self, t, d):
        self.dialog_triggers.append(t)
        return Handle('event')

    def n_TriggerRegisterPlayerEvent(self, t, p, ev):
        self.leave_triggers.append((t, p.pid, ev.value))
        return Handle('event')

    def n_TriggerRegisterPlayerChatEvent(self, t, p, s, exact):
        self.chat_triggers.append((t, p.pid, s))
        return Handle('event')

    def n_GetTriggerUnit(self):
        return self.ctx_get('unit')

    def n_GetKillingUnit(self):
        return self.ctx_get('killer')

    def n_GetTriggerPlayer(self):
        return self.ctx_get('player')

    def n_GetClickedButton(self):
        return self.ctx_get('button')

    def n_ExecuteFunc(self, name):
        if name not in self.vm.p.functions:
            self.vm.report('ExecuteFunc of unknown function %s (crashes the game)' % name)
        params = self.vm.p.functions[name][0]
        if params:
            self.vm.report('ExecuteFunc of %s which takes arguments' % name)
        self.vm.run(name, thread='ExecuteFunc ' + name)

    def n_TriggerEvaluate(self, t):
        return True

    def n_TriggerExecute(self, t):
        self.fire(t, {})

    # dialogs ------------------------------------------------------------

    def n_DialogAddButton(self, d, text, hotkey):
        b = Handle('button')
        b.text = text
        self.dialog_buttons.setdefault(d.hid, []).append(b)
        return b

    # text ---------------------------------------------------------------

    def n_DisplayTimedTextToPlayer(self, p, x, y, dur, msg):
        if p.pid == min(self.users):
            self.messages.append((self.time, msg))

    def n_DisplayTextToPlayer(self, p, x, y, msg):
        self.n_DisplayTimedTextToPlayer(p, x, y, 0, msg)

    def n_I2S(self, i):
        return str(i)

    def n_R2S(self, r):
        return '%.3f' % r

    def n_R2I(self, r):
        return int(r)

    def n_I2R(self, i):
        return float(i)

    def n_S2I(self, s):
        try:
            return int(s)
        except Exception:
            return 0

    def n_StringLength(self, s):
        return len(s or '')

    def n_SubString(self, s, a, b):
        return (s or '')[a:b]

    def n_StringCase(self, s, upper):
        return (s or '').upper() if upper else (s or '').lower()

    def n_SquareRoot(self, v):
        return math.sqrt(max(0.0, v))

    def n_Cos(self, v):
        return math.cos(v)

    def n_Sin(self, v):
        return math.sin(v)

    def n_Atan2(self, y, x):
        return math.atan2(y, x)

    def n_Pow(self, a, b):
        return float(a) ** b

    def n_GetRandomInt(self, a, b):
        if a > b:
            a, b = b, a
        return self.rng.randint(a, b)

    def n_GetRandomReal(self, a, b):
        return self.rng.uniform(a, b)

    def n_CreateTextTag(self):
        self.texttags += 1
        return Handle('texttag')

    def f_CustomVictoryBJ(self, p, a, b):
        self.victory.add(p.pid)

    def f_CustomDefeatBJ(self, p, msg):
        self.defeat.add(p.pid)

    # world actions used by scenarios ---------------------------------------

    def kill(self, u, killer):
        if u is None or not u.alive:
            return
        u.life = 0.0
        ev = self.vm.g['EVENT_PLAYER_UNIT_DEATH'].value
        for t in self.event_triggers.get((ev, u.owner.pid), []):
            self.fire(t, {'unit': u, 'killer': killer, 'player': u.owner})
        if not u.is_hero:
            self.units.remove(u)

    def click(self, pid, text):
        for buttons in self.dialog_buttons.values():
            for b in buttons:
                if b.text == text:
                    for t in self.dialog_triggers:
                        self.fire(t, {'button': b, 'player': self.n_Player(pid)})
                    return
        raise AssertionError('no dialog button %r' % text)

    def chat(self, pid, text):
        for t, p, s in self.chat_triggers:
            if p == pid and s == text:
                self.fire(t, {'player': self.n_Player(pid)})

    def leave(self, pid):
        for t, p, ev in self.leave_triggers:
            if p == pid:
                self.fire(t, {'player': self.n_Player(pid)})

    def advance(self, until):
        while self.timers and self.timers[0][0] <= until:
            due, _, t, gen = heapq.heappop(self.timers)
            if gen != t.gen or t.due is None:
                continue
            self.time = due
            if t.periodic:
                t.due = due + t.period
                self.timer_seq += 1
                heapq.heappush(self.timers, (t.due, self.timer_seq, t, t.gen))
            else:
                t.due = None
            self.ctx.append({'timer': t})
            try:
                self.vm.run(t.func.name, thread='timer ' + t.func.name)
            finally:
                self.ctx.pop()
        self.time = until

    def units_of(self, pid, uid=None):
        return [u for u in self.units if u.owner.pid == pid and u.alive
                and (uid is None or fourcc(u.uid) == uid)]


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def load(paths):
    prog = Program()
    for path in paths:
        with open(path, encoding='utf-8', errors='replace') as f:
            src = f.read()
        Parser(lex(src, path), path).parse_file(prog)
    return prog


def boot(paths, users, seed):
    prog = load(paths)
    world = World(users, seed)
    vm = Interp(prog, world)
    vm.init_globals()
    vm.run('config')
    vm.run('main')
    return world, vm


def check(cond, msg, failures):
    if not cond:
        failures.append(msg)


def scenario_full_game(world, vm, failures):
    """Two players: pick heroes, clear camps, take outposts, kill bosses,
    return the urn, survive raids and win."""
    g = vm.g
    P = world.n_Player
    creep = P(g['PLAYER_NEUTRAL_AGGRESSIVE'])
    world.advance(1.0)
    world.click(0, 'Paladin')
    world.click(1, 'Random (+150 gold)')
    world.advance(3.0)
    h0, h1 = g['hero'][0], g['hero'][1]
    check(h0 is not None and h1 is not None, 'heroes were not created', failures)
    check(world.n_GetPlayerState(P(1), g['PLAYER_STATE_RESOURCE_GOLD']) == 750, 'random hero bonus gold missing', failures)
    world.chat(0, '-help')

    # clear every camp and the outpost guards
    for u in list(world.units_of(creep.pid)):
        if 100 <= u.data < 200:
            world.kill(u, h0)
    world.advance(10.0)
    # walk the heroes to each outpost
    for o in range(g['outpostCount']):
        ox, oy = g['outpostX'][o], g['outpostY'][o]
        if g['outpostOwner'][o] == g['SCOURGE_ID']:
            for u in world.units_of(5):
                if math.hypot(u.x - ox, u.y - oy) < 900:
                    world.kill(u, h1)
        h0.x, h0.y = ox + 100, oy
        world.advance(world.time + 2.0)
        check(g['outpostOwner'][o] == 0, 'outpost %d was not claimed (owner %r)' % (o, g['outpostOwner'][o]), failures)
    check(g['frontierDone'], 'frontier quest not completed', failures)
    gold_before = world.n_GetPlayerState(P(0), g['PLAYER_STATE_RESOURCE_GOLD'])
    world.advance(world.time + 30.0)
    gold_after = world.n_GetPlayerState(P(0), g['PLAYER_STATE_RESOURCE_GOLD'])
    check(gold_after > gold_before, 'outpost income not paid', failures)

    # bosses
    for u in list(world.units_of(creep.pid)):
        if 300 <= u.data < 500:
            world.kill(u, h1)
    check(g['urnDropped'], 'urn not dropped', failures)
    world.n_UnitAddItemById(h1, 0x6B74726D)  # 'ktrm'
    h1.x, h1.y = g['castleX'], g['castleY'] + 300
    world.advance(world.time + 2.0)
    check(g['urnReturned'], 'urn delivery not detected', failures)

    # hero death and revival
    world.kill(h0, None)
    world.advance(world.time + 60.0)
    check(h0.alive, 'hero was not revived', failures)

    # raids for 25 minutes, killing most raiders as they come
    for minute in range(25):
        world.advance(world.time + 60.0)
        for u in world.units_of(5):
            if u.data == 500 and world.rng.random() < 0.8:
                world.kill(u, h0)
        if minute == 3:
            world.leave(1)
    check(g['raidWave'] >= 8, 'too few raids happened: %d' % g['raidWave'], failures)
    # respawned camps exist again
    camps_alive = sum(1 for u in world.units_of(creep.pid) if 100 <= u.data < 200)
    check(camps_alive > 0, 'camps did not respawn', failures)

    # creep XP for high level heroes
    h0.hero_level = 7
    xp = h0.xp
    for u in list(world.units_of(creep.pid)):
        if 100 <= u.data < 200:
            h0.x, h0.y = u.x, u.y
            world.kill(u, h0)
            break
    check(h0.xp > xp, 'no bonus XP for a level 7 hero', failures)

    # win
    world.kill(g['lich'], h0)
    check(not world.victory, 'victory before the citadel fell', failures)
    world.kill(g['citadel'], h0)
    world.advance(world.time + 5.0)
    check(0 in world.victory, 'no victory after lich and citadel died', failures)


def scenario_defeat(world, vm, failures):
    world.advance(50.0)
    check(vm.g['hero'][2] is not None, 'hero not auto-picked after the timeout', failures)
    world.advance(20 * 60.0)
    world.kill(vm.g['castle'], None)
    world.advance(world.time + 3.0)
    check(vm.g['gameOver'] and 2 in world.defeat, 'defeat not triggered by the castle dying', failures)


def scenario_four_players(world, vm, failures):
    world.advance(1.0)
    for i, name in enumerate(['Archmage', 'Blademaster', 'Demon Hunter', 'Pandaren Brewmaster']):
        world.click(i, name)
    # nobody fights back: the Scourge takes over and keeps raiding
    world.advance(45 * 60.0)
    check(vm.g['raidWave'] >= 15, 'raids stalled: %d' % vm.g['raidWave'], failures)


SCENARIOS = {
    'full': ([0, 1], 1, scenario_full_game),
    'defeat': ([2], 2, scenario_defeat),
    'four': ([0, 1, 2, 3], 3, scenario_four_players),
}


def main(argv):
    paths = [a for a in argv if not a.startswith('--')]
    only = [a[len('--scenario='):] for a in argv if a.startswith('--scenario=')]
    verbose = '--verbose' in argv
    if len(paths) != 3:
        print(__doc__)
        return 2
    ok = True
    for name, (users, seed, fn) in SCENARIOS.items():
        if only and name not in only:
            continue
        world, vm = boot(paths, users, seed)
        failures = []
        try:
            fn(world, vm, failures)
        except Exception as e:  # a broken script can leave the world half set up
            failures.append('scenario aborted: %r' % (e,))
        print('scenario %-7s: %d units alive, %d messages, raid wave %d, %d runtime errors, %d failed checks'
              % (name, len([u for u in world.units if u.alive]), len(world.messages), vm.g['raidWave'],
                 len(vm.errors), len(failures)))
        for e in vm.errors:
            print('  runtime error:', e)
        for f in failures:
            print('  check failed:', f)
        if verbose:
            for t, m in world.messages:
                print('  %7.1f  %s' % (t, m))
        ok = ok and not vm.errors and not failures
    print('OK' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
