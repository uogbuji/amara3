'''
Raw XML writer
'''

from enum import Enum #https://docs.python.org/3.4/library/enum.html

from amara3.uxml import tree, xml

class token(Enum):
    start_open = 1
    start_close = 2
    end_open = 3
    end_close = 4
    attr_quote = 5
    between_attr = 6
    pre_attr = 7
    attr_equals = 8


TOKENS = {
    token.start_open: '<',
    token.start_close: '>',
    token.end_open: '</',
    token.end_close: '>',
    token.attr_quote: '"',
    token.pre_attr: ' ',
    token.between_attr: ' ',
    token.attr_equals: '=',
}


class context(Enum):
    start_element = 1
    end_element = 2
    element_name = 3
    attribute_name = 4
    attribute_text = 5
    text = 6


class raw(object):
    '''
    >>> import io
    >>> from amara3.uxml import writer
    >>> fp = io.StringIO() #or is it better to use BytesIO?
    >>> w = writer.raw(fp)
    >>> w.start_element('spam')
    >>> w.text('eggs')
    >>> w.end_element('spam')
    >>> fp.getvalue()
    '<spam>eggs</spam>'   
    '''
    def __init__(self, fp=None, whandler=None):
        #FIXME: check that fp *or* whandler are not None
        self._fp = fp
        self._whandler = whandler(fp) if whandler else self
        return

    def write(self, ctx, text):
        if ctx in (context.text, context.attribute_text):
            text = escape(text)
        if isinstance(text, token): text = TOKENS[text]
        self._fp.write(text)
        return

    def start_element(self, name, attribs=None):
        attribs = attribs or {}
        self._whandler.write(context.start_element, token.start_open)
        self._whandler.write(context.element_name, name)
        first_attribute = True
        for k, v in attribs.items():
            if first_attribute:
                self._whandler.write(context.start_element, token.pre_attr)
                first_attribute = False
            else:
                self._whandler.write(context.start_element, token.between_attr)
            self._whandler.write(context.attribute_name, k)
            self._whandler.write(context.start_element, token.attr_equals)
            self._whandler.write(context.start_element, token.attr_quote)
            self._whandler.write(context.attribute_text, v)
            self._whandler.write(context.start_element, token.attr_quote)
        self._whandler.write(context.start_element, token.start_close)
        return

    def end_element(self, name):
        self._whandler.write(context.end_element, token.end_open)
        self._whandler.write(context.element_name, name)
        self._whandler.write(context.end_element, token.end_close)
        return

    def text(self, text):
        self._whandler.write(context.text, text)
        return


class namespacer(raw):
    '''
    Writer that adds namespace information to output
    
    mapping = {}
    
    >>> import io
    >>> from amara3.uxml import writer
    >>> fp = io.StringIO()
    >>> w = writer.raw(fp)
    >>> w.start_element('spam')
    >>> w.text('eggs')
    >>> w.end_element('spam')
    >>> fp.getvalue()
    '<spam>eggs</spam>'   
    '''
    def __init__(self, fp, whandler=None, prefixes=None, mapping=None):
        raw.__init__(self, fp=fp, whandler=whandler)
        self._mapping = mapping or {}
        self._prefixes = prefixes or {}
        self._first_element = True
        return

    def start_element(self, name, attribs=None):
        self._ns_handled = False
        raw.start_element(self, name, attribs=attribs)
        self._first_element = False

    def write(self, ctx, text):
        if ctx in (context.text, context.attribute_text):
            text = escape(text)
        if ctx == context.start_element:
            if self._first_element and text in (token.pre_attr, token.start_close) and not self._ns_handled:
                #Namespace declarations here
                for k, v in self._prefixes.items():
                    self._fp.write(TOKENS[token.pre_attr])
                    self._fp.write('xmlns:' + k if k else 'xmlns')
                    self._fp.write(TOKENS[token.attr_equals])
                    self._fp.write(TOKENS[token.attr_quote])
                    self._fp.write(v)
                    self._fp.write(TOKENS[token.attr_quote])
                #self._fp.write(TOKENS[token.pre_attr])
                self._ns_handled = True
        if ctx == context.element_name:
            #Include prefix, if there's one
            prefix = self._mapping.get(text, ('', ''))[1]
            if prefix:
                self._fp.write(prefix + ':')
        if ctx == context.attribute_name:
            #Include prefix, if there's one
            prefix = self._mapping.get('@' + text, ('', ''))[1]
            if prefix:
                self._fp.write(prefix + ':')
        if isinstance(text, token): text = TOKENS[text]
        self._fp.write(text)
        return


#Write an XML element node
def write(elem, writer):
    writer.start_element(elem.xml_name, attribs=elem.xml_attributes)
    for node in elem.xml_children:
        if isinstance(node, tree.element):
            write(node, writer)
        elif isinstance(node, tree.text):
            writer.text(node)
    writer.end_element(elem.xml_name)
    return