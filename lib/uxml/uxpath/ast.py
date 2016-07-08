# amara3.uxml.uxpath.ast

'''Abstract Syntax Tree for parsed MicroXPath.

Heavy debt to: https://github.com/emory-libraries/eulxml/blob/master/eulxml/xpath/ast.py
'''

#Q=a; python -c "from amara3.uxml import tree; tb = tree.treebuilder(); root = tb.parse('<a><b i=\"1.1\"><x>1</x></b><c i=\"1.2\"><x>2</x><d><x>3</x></d></c><x>4</x><y>5</y></a>'); from amara3.uxml.uxpath import context, parse as uxpathparse; ctx = context(root); parsed_expr = uxpathparse('$Q'); result = parsed_expr.compute(ctx); print(list(result))"

__all__ = [
    'serialize',
    'UnaryExpression',
    'BinaryExpression',
    'PredicateExpression',
    'AbsolutePath',
    'Step',
    'NameTest',
    'NodeType',
    'AbbreviatedStep',
    'VariableReference',
    'FunctionCall',
    ]


import operator
from amara3.uxml.tree import node, element
from amara3.uxml.treeutil import descendants


class root_node(node):
    _cache = {}
    
    def __init__(self, docelem):
        self.xml_name = ''
        self.xml_value = ''
        self.xml_children = [docelem]
        node.__init__(self)

    def __repr__(self):
        return u'{uxpath.rootnode}'
    
    @staticmethod
    def get(elem):
        if isinstance(elem, root_node):
            return elem
        assert isinstance(elem, element)
        eparent = elem.xml_parent
        while eparent:
            eparent = eparent.xml_parent
        return root_node._cache.setdefault(elem, root_node(elem))


class attribute_node(node):
    def __init__(self, name, value, parent):
        self.xml_name = name
        self.xml_value = value
        node.__init__(self, parent)

    def __repr__(self):
        return u'{{uxpath.attribute {0}="{1}"}}'.format(self.xml_name, self.xml_value)


def index_docorder(node):
    #Always start at the root
    while node.xml_parent:
        node = node.xml_parent
    index = 0
    node._docorder = index
    for node in descendants(node):
        index += 1
        node._docorder = index


def strval(n, accumulator=None, outermost=True):
    '''
    MicroXPath string value of node
    '''
    if isinstance(n, attribute_node):
        return n.xml_value
    else:
        #Element, text or root node
        accumulator = accumulator or []
        for child in n.xml_children:
            if isinstance(child, str):
                accumulator.append(child.xml_value)
            elif isinstance(child, element):
                accumulator.extend(strval(child, accumulator=accumulator, outermost=False))
        if outermost: accumulator = ''.join(accumulator)
        return accumulator


#Casts
def to_number(seq):
    '''
    Cast an arbitrary sequence to a number type
    '''
    val = next(seq, None)
    if val is None:
        #FIXME: Should be NaN, not 0
        yield 0
    elif isinstance(val, str):
        yield float(val)
    elif isinstance(val, node):
        yield float(strval(val))


def to_boolean(seq):
    '''
    Cast an arbitrary sequence to a boolean type
    '''
    val = next(seq, None)
    if val is None:
        yield False
    elif isinstance(val, str):
        yield bool(str)
    elif isinstance(val, node):
        yield True


class UnaryExpression(object):
    '''A unary XPath expression. Really only used with unary minus (self.op == '-')'''

    def __init__(self, op, right):
        assert op == '-'
        self.op = op
        '''the operator used in the expression'''
        self.right = right
        '''the expression the operator is applied to'''

    def __repr__(self):
        return '{{{} {} {}}}'.format(self.__class__.__name__, self.op, serialize(self))

    def _serialize(self):
        yield(self.op)
        for tok in _serialize(self.right):
            yield(tok)

    def __call__(self, ctx):
        '''
        Alias for user convenience
        '''
        yield from self.compute(ctx)

    def compute(self, ctx):
        #self.op is always '-'
        yield -(to_number(next(self.right.compute(ctx), None)))


BE_KEYWORDS = set(['or', 'and', 'div', 'mod'])
class BinaryExpression(object):
    '''Binary XPath expression, e.g. a/b; a and b; a | b.'''

    def __init__(self, left, op, right):
        self.left = left
        '''the left side of the binary expression'''
        self.op = op
        '''the operator of the binary expression'''
        self.right = right
        '''the right side of the binary expression'''

    def __repr__(self):
        return '{{{} {} {} {}}}'.format(self.__class__.__name__, serialize(self.left), self.op, serialize(self.right))

    def _serialize(self):
        for tok in _serialize(self.left):
            yield(tok)

        if self.op in BE_KEYWORDS:
            yield(' ')
            yield(self.op)
            yield(' ')
        else:
            yield(self.op)

        for tok in _serialize(self.right):
            yield(tok)

    def __call__(self, ctx):
        '''
        Alias for user convenience
        '''
        yield from self.compute(ctx)

    def compute(self, ctx):
        #print('BinaryExpression', (self.left, self.op, self.right))
        if self.op == '/':
            #left & right are steps
            selected = self.left.compute(ctx)
            for node in selected:
                new_ctx = ctx.copy(node=node)
                yield from self.right.compute(new_ctx)
        elif self.op == '//':
            #left & right are steps
            #Rewrite the axis to expand the abbreviation
            #Really only needed the first time.
            self.right.axis = 'descendant-or-self'
            selected = self.left.compute(ctx)
            for node in selected:
                new_ctx = ctx.copy(node=node)
                yield from self.right.compute(new_ctx)
        elif self.op == '|':
            #Union expressions require an indexing by doc order
            if not hasattr(ctx.node, '_docorder'):
                index_docorder(ctx.node)
            #XXX Might be more efficient to maintain a list in doc order as left & right are added
            selected = list(self.left.compute(ctx))
            selected.extend(list(self.right.compute(ctx)))
            selected.sort(key=operator.attrgetter('_docorder'))
            yield from selected
        return


class PredicateExpression(object):
    '''
    Filtered XPath expression. $var[1]; (a or b)[foo][@bar]
    '''
    def __init__(self, base, predicates=None):
        #base expression to be filtered
        self.base = base
        #list of filter predicates
        self.predicates = predicates or []

    def __repr__(self):
        return '{{{} {}}}'.format(self.__class__.__name__, serialize(self))

    def append_predicate(self, pred):
        self.predicates.append(pred)

    def _serialize(self):
        yield('(')
        for tok in _serialize(self.base):
            yield(tok)
        yield(')')
        for pred in self.predicates:
            yield('[')
            for tok in _serialize(pred):
                yield(tok)
            yield(']')

    def __call__(self, ctx):
        '''
        Alias for user convenience
        '''
        yield from self.compute(ctx)

    def compute(self, ctx):
        #raise Exception(('GRIPPO', self.predicates))
        for item in self.base.compute(ctx):
            for pred in self.predicates:
                if not to_boolean(pred.compute(ctx)):
                    break
            else:
                #All predicates true
                yield(item)


class AbsolutePath(object):
    '''
    Absolute XPath path. /a/b/c; //a/ancestor:b/@c
    '''
    def __init__(self, op='/', relative=None):
        #Operator used to root the expression
        self.op = op
        #Relative path after the absolute root operator
        self.relative = relative

    def __repr__(self):
        if self.relative:
            return '{{{} {} {}}}'.format(self.__class__.__name__, self.op, serialize(self.relative))
        else:
            return '{{{} {}}}'.format(self.__class__.__name__, self.op)

    def _serialize(self):
        yield(self.op)
        for tok in _serialize(self.relative):
            yield(tok)

    def __call__(self, ctx):
        '''
        Alias for user convenience
        '''
        yield from self.compute(ctx)

    def compute(self, ctx):
        rnode = root_node.get(ctx.node)
        if self.relative:
            new_ctx = ctx.copy(node=rnode)
            yield from self.relative.compute(new_ctx)
        else:
            yield rnode


class Step(object):
    '''
    Single step in a relative path. a; @b; text(); parent::foo:bar[5]
    '''
    def __init__(self, axis, node_test, predicates):
        self.axis = axis or 'child'
        #NameTest or NodeType object used to select from nodes in the axis
        self.node_test = node_test
        #list of predicates filtering the step's results
        self.predicates = predicates

    def __repr__(self):
        return '{{{} {}}}'.format(self.__class__.__name__, serialize(self))

    def _serialize(self):
        if self.axis == 'attribute':
            yield('@')
        elif self.axis:
            yield self.axis
            yield('::')

        for tok in self.node_test._serialize():
            yield(tok)

        for predicate in self.predicates:
            yield('[')
            for tok in _serialize(predicate):
                yield(tok)
            yield(']')

    def raw_compute(self, ctx):
        #print('STEP', (self.axis, self.node_test, self.predicates))
        if self.axis == 'self':
            yield from self.node_test.compute(ctx)
        elif self.axis == 'child':
            for node in ctx.node.xml_children:
                new_ctx = ctx.copy(node=node)
                yield from self.node_test.compute(new_ctx)
        elif self.axis == 'attribute':
            for k, v in ctx.node.xml_attributes.items():
                if self.node_test.name in ('*', v):
                    yield attribute_node(k, v, ctx.node)
        elif self.axis == 'ancestor':
            node = ctx.node.xml_parent
            while node:
                new_ctx = ctx.copy(node=node)
                yield from self.node_test.compute(new_ctx)
                node = node.xml_parent
            yield root_node.get(node)
        elif self.axis == 'ancestor-or-self':
            yield from self.node_test.compute(ctx)
            node = ctx.node.xml_parent
            while node:
                new_ctx = ctx.copy(node=node)
                yield from self.node_test.compute(new_ctx)
            yield root_node.get(node)
        elif self.axis == 'descendant':
            to_process = list(ctx.node.xml_children)
            while to_process:
                node = to_process[0]
                to_process = list(node.xml_children) + to_process[1:]
                new_ctx = ctx.copy(node=node)
                yield from self.node_test.compute(new_ctx)
        elif self.axis == 'descendant-or-self':
            yield from self.node_test.compute(ctx)
            to_process = list(ctx.node.xml_children)
            while to_process:
                node = to_process[0]
                to_process = list(node.xml_children) + to_process[1:]
                new_ctx = ctx.copy(node=node)
                yield from self.node_test.compute(new_ctx)
        elif self.axis == 'following':
            if not ctx.node.xml_parent: return
            start = ctx.node.xml_parent.xml_children.index(ctx.node) + 1
            to_process = list(ctx.node.xml_parent.xml_children)[start:]
            while to_process:
                node = to_process[0]
                to_process = list(node.xml_children) + to_process[1:]
                new_ctx = ctx.copy(node=node)
                yield from self.node_test.compute(new_ctx)
        elif self.axis == 'following-sibling':
            if not ctx.node.xml_parent: return
            start = ctx.node.xml_parent.xml_children.index(ctx.node) + 1
            for node in list(ctx.node.xml_parent.xml_children)[start:]:
                new_ctx = ctx.copy(node=node)
                yield from self.node_test.compute(new_ctx)
        elif self.axis == 'parent':
            if ctx.node.xml_parent:
                new_ctx = ctx.copy(node=node.xml_parent)
                yield from self.node_test.compute(new_ctx)
            else:
                yield root_node.get(node)
        elif self.axis == 'preceding':
            if not ctx.node.xml_parent: return
            start = ctx.node.xml_parent.xml_children.index(ctx.node) - 1
            if start == -1: return
            to_process = list(ctx.node.xml_parent.xml_children)[:start].reverse()
            while to_process:
                node = to_process[0]
                to_process = to_process[1:] + list(node.xml_children).reverse()
                new_ctx = ctx.copy(node=node)
                yield from self.node_test.compute(new_ctx)
        elif self.axis == 'preceding-sibling':
            if not ctx.node.xml_parent: return
            start = ctx.node.xml_parent.xml_children.index(ctx.node) - 1
            if start == -1: return
            to_process = list(ctx.node.xml_parent.xml_children)[start:].reverse()
            for node in to_process:
                new_ctx = ctx.copy(node=node)
                yield from self.node_test.compute(new_ctx)
        return

    def __call__(self, ctx):
        '''
        Alias for user convenience
        '''
        yield from self.compute(ctx)

    def compute(self, ctx):
        if not self.predicates:
            yield from self.raw_compute(ctx)
            return
        count = 0
        for item in self.raw_compute(ctx):
            count += 1 #XPath is 1-indexed
            new_ctx = ctx.copy(node=item)
            for pred in self.predicates:
                if isinstance(pred, float) or isinstance(pred, int):
                    if count != int(pred):
                        break
                elif not to_boolean(pred.compute(new_ctx)):
                    break
            else:
                #All predicates true
                yield(item)


class NameTest(object):
    '''
    Element name node test for a Step.
    '''
    def __init__(self, name):
        #XML name or '*'
        self.name = name

    def __repr__(self):
        return '{{{} {}}}'.format(self.__class__.__name__, serialize(self))

    def _serialize(self):
        yield(self.name)

    def __str__(self):
        return ''.join(self._serialize())

    def __call__(self, ctx):
        '''
        Alias for user convenience
        '''
        yield from self.compute(ctx)

    def compute(self, ctx):
        #print('NameTest', (self.name, ctx.node))
        if self.name == '*':
            yield ctx.node
        else:
            #yield from (n for n in nodeseq if n.xml_name == self.name)
            if isinstance(ctx.node, element) and ctx.node.xml_name == self.name:
                yield ctx.node


class NodeType(object):
    '''
    Node type node test for a Step.
    '''
    def __init__(self, name):
        #node type name, 'node' or 'text'
        self.name = name

    def __repr__(self):
        return '{{{} {}}}'.format(self.__class__.__name__, serialize(self))

    def _serialize(self):
        yield(self.name)
        yield('(')
        if self.literal is not None:
            for tok in _serialize(self.literal):
                yield(self.literal)
        yield(')')

    def __str__(self):
        return ''.join(self._serialize())

    def __call__(self, ctx):
        '''
        Alias for user convenience
        '''
        yield from self.compute(ctx)

    def compute(self, ctx):
        if self.name == 'node' or isinstance(ctx.node, str):
            yield ctx.node


class AbbreviatedStep(object):
    '''
    Abbreviated XPath step. '.' or '..'
    '''
    def __init__(self, abbr):
        #abbreviated step
        self.abbr = abbr

    def __repr__(self):
        return '{{{} {}}}'.format(self.__class__.__name__, serialize(self))

    def _serialize(self):
        yield(self.abbr)

    def raw_compute(self, ctx):
        #print('STEP', (self.axis, self.node_test, self.predicates))
        #self axis
        if self.abbr == '.':
            yield from self.node_test.compute(ctx)
        #parent axis
        elif self.abbr == '..':
            if ctx.node.xml_parent:
                new_ctx = ctx.copy(node=node.xml_parent)
                yield from self.node_test.compute(new_ctx)
            else:
                yield root_node.get(node)

    def __call__(self, ctx):
        '''
        Alias for user convenience
        '''
        yield from self.compute(ctx)

    compute = Step.compute


class VariableReference(object):
    '''
    XPath variable reference, e.g. '$foo'
    '''
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '{{{} {}}}'.format(self.__class__.__name__, serialize(self))

    def _serialize(self):
        yield('$')
        yield(self.name)

    def __call__(self, ctx):
        '''
        Alias for user convenience
        '''
        yield from self.compute(ctx)

    def compute(self, ctx):
        yield from ctx.variables[self.name]


class FunctionCall(object):
    '''
    XPath function call, e.g. 'foo()'; 'foo(1, 'a', $var)'
    '''
    def __init__(self, name, args):
        self.name = name
        #list of argument expressions
        self.args = args

    def __repr__(self):
        return '{{{} {}}}'.format(self.__class__.__name__, serialize(self))

    def _serialize(self):
        yield(self.name)
        yield('(')
        if self.args:
            for tok in _serialize(self.args[0]):
                yield(tok)

            for arg in self.args[1:]:
                yield(',')
                for tok in _serialize(arg):
                    yield(tok)
        yield(')')

    def __call__(self, ctx):
        '''
        Alias for user convenience
        '''
        yield from self.compute(ctx)

    def compute(self, ctx):
        if not self.name in ctx.functions:
            #FIXME: g11n
            raise RuntimeError('Unknown function: {}'.format(self.name))
        func = ctx.functions[self.name]
        yield from func(ctx, *self.args)


class Sequence(object):
    '''
    MicroXPath sequence, e.g. '()'; '(1, 'a', $var)'
    '''
    def __init__(self, items):
        #list of argument expressions
        self.items = items

    def __repr__(self):
        return '{{{} {}}}'.format(self.__class__.__name__, serialize(self))

    def _serialize(self):
        yield('(')
        if self.items:
            for tok in _serialize(self.items[0]):
                yield(tok)

            for item in self.items[1:]:
                yield(',')
                for tok in _serialize(item):
                    yield(tok)
        yield(')')

    def __call__(self, ctx):
        '''
        Alias for user convenience
        '''
        yield from self.compute(ctx)

    def compute(self, ctx):
        for item in self.items:
            if hasattr(item, 'compute'):# and iscallable(item.compute):
                yield from item.compute(ctx)
            else:
                yield item


def serialize(xp_ast):
    '''Serialize an XPath AST as a valid XPath expression.'''
    return ''.join(_serialize(xp_ast))


def _serialize(xp_ast):
    '''Generate token strings which, when joined together, form a valid
    XPath serialization of the AST.'''

    if hasattr(xp_ast, '_serialize'):
        for tok in xp_ast._serialize():
            yield(tok)
    elif isinstance(xp_ast, str):
        yield(repr(xp_ast))
