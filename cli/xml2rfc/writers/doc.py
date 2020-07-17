# Copyright The IETF Trust 2018, All Rights Reserved
# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, division

import collections
import datetime
import io
import jinja2
import lxml
import os
import pydoc
import re
import yaml

from xml2rfc import debug, __version__
from xml2rfc.utils import namespaces
from xml2rfc.writers import base

debug = debug                           # silence pyflakes


def capfirst(value):
    """Capitalize the first character of the value."""
    return value and value[0].upper() + value[1:]

class DocWriter(base.BaseV3Writer):
    def __init__(self, xmlrfc, quiet=None, options=base.default_options, date=datetime.date.today()):
        super(DocWriter, self).__init__(xmlrfc, quiet=quiet, options=options, date=date)
        rfc7991_rng_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'rfc7991.rng')
        self.rfc7991_schema = lxml.etree.ElementTree(file=rfc7991_rng_file)
        self.template_dirs = list(filter(None, [ options.template_dir, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates') ]))
        self.jinja = jinja2.Environment(
            loader = jinja2.FileSystemLoader(self.template_dirs),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.jinja.filters['capfirst'] = capfirst
        self.rendered = None

    def get_elements(self):
        elements = {}
        parents = collections.defaultdict(set)
        attribtag = '{%s}attribute'%namespaces['x']
        ignored_attributes = [

            'xml:base',
            'xml:lang',
            'xml:space',

            'derivedAnchor',
            'derivedContent',
            'derivedCounter',
            'derivedLink',
            'displayFormat',
            'expiresDate',
            'mode',
            'originalSrc',
            'pn',
            'quoteTitle',
            'pageno',
            'scripts',
            'slugifiedName',

        ]

        #debug.show('attribtag')
        edefs = self.v3_schema.xpath("/x:grammar/x:define/x:element", namespaces=namespaces)
        rnc = RelaxNGCompactRenderer()
        rnc.render(self.v3_schema.getroot())
        for element in edefs:
            ename = element.get('name')
            is_new = self.rfc7991_schema.xpath("/x:grammar/x:define/x:element[@name='%s']" % ename, namespaces=namespaces) == []
            e = {'attributes': [], 'children': [], 'rnc': [], 'parents': [], 'new': is_new, }
            elements[ename] = e
            #debug.show('ename')
            for a in element.xpath('.//x:attribute', namespaces=namespaces):
                aname = a.get('name')
                if aname in ignored_attributes:
                    continue
                adict = {'name': aname}
                e['attributes'].append(adict)
                adict['required'] = a.getparent().tag != '{http://relaxng.org/ns/structure/1.0}optional'
                default = a.get('{http://relaxng.org/ns/compatibility/annotations/1.0}defaultValue')
                if default:
                    adict['default'] = default
                choices = a.xpath('x:choice/x:value', namespaces=namespaces)
                if choices:
                    adict['choices'] = [ dict(value=v.text) for v in choices ]
                    adict['rnc'] = rnc.render(a.getchildren()[0])
                adict['new'] = self.rfc7991_schema.xpath("/x:grammar/x:define/x:element[@name='%s']//x:attribute[@name='%s']" % (ename, aname), namespaces=namespaces) == []
                adict['deprecated'] = (ename, aname) in base.deprecated_attributes
                #debug.show("e['attributes']")
            for c in element.getchildren():
                if c.tag != attribtag and c.find(attribtag) == None:
                    e['children'].append((c, rnc.render(c)))
                    cnames = element.xpath('.//x:ref/@name', namespaces=namespaces)
                    for cname in cnames:
                        parents[cname].add(ename)
            e['attributes'].sort(key=lambda x: x['name'])
            e['deprecated_attributes'] = any(a['deprecated'] for a in e['attributes'])
            e['rnc'] = ', '.join(filter(None, [ c[1] for c in e['children'] ]))
        for k, v in parents.items():
            if k in elements:
                elements[k]['parents'] = list(v)
                elements[k]['parents'].sort()
            
        return elements


    def process(self):
        from xml2rfc.run import optionparser
        if self.rendered:
            return self.rendered

        template = self.jinja.get_template('doc.xml')

        elements = self.get_elements()

        for dir in self.template_dirs:
            fn = os.path.join(dir, 'doc.yaml')
            if os.path.exists(fn):
                with io.open(fn) as file:
                    text = file.read()
                    text = text.replace(r'\<', r'&lt;').replace(r'\>', r'&gt;').replace(r'\&', r'&amp;')
                    descriptions = yaml.load(text, Loader=yaml.FullLoader)

        for n, d in elements.items():
            d['description'] = descriptions.get(n, None)
            for dd in d['attributes']:
                a = dd['name']
                dd['description'] = descriptions.get('%s[%s]' % (n,a), None)
                choices = dd.get('choices', [])
                for ddd in choices:
                    c = ddd['value']
                    ddd['description'] = descriptions.get('%s[%s="%s"]' % (n,a, c), None)
                dd['choice_descriptions'] = any(ddd['description'] for ddd in choices)
        element_list = [ {'tag': t, 'deprecated': t in base.deprecated_element_tags } for t in base.element_tags ]
        element_list.sort(key=lambda x: x['tag'])

        for d in element_list:
            d.update(elements[d['tag']])

        context = {}
        context['elements'] = element_list
        context['element_tags'] = list(base.element_tags)
        context['options'] = optionparser
        context['toc_depth'] = getattr(self.options, 'toc_depth', "2")
        context['v3_element_tags'] = list(base.element_tags-base.deprecated_element_tags)
        context['version'] =  __version__
        context['descriptions'] = descriptions
        with open(self.v3_rnc_file) as file:
            context['schema'] = ('\n' + file.read()).replace('\n   ', '\n')

        descriptions['-context-'] = {}
        descriptions['-context-']['descriptions']    = "The descriptions read from the <tt>doc.yaml</tt> file"
        descriptions['-context-']['element_tags']    = "A list of all the element tags in the XML schema"
        descriptions['-context-']['elements']        = ("A list of dictionaries, each with information about one schema element: "
            '{'+''.join( '"%s": ..., '% k for k in sorted(element_list[0].keys())) +'}')
        descriptions['-context-']['options']         = "A list of dictionaries describing the command-line options"
        descriptions['-context-']['schema']          = "The full RelaxNG Compact representation of the schema in text form"
        descriptions['-context-']['toc_depth']       = "ToC depth setting; 1 when running --man, 2 otherwise"
        descriptions['-context-']['v3_element_tags'] = "A list of v3 element tags, excluding deprecated tags"
        descriptions['-context-']['version']         = "The xml2rfc version number"

        # context meta-information
        context['context'] = context


        self.rendered = template.render(context)

        return self.rendered

    def manpage(self):
        import xml2rfc
        parser = xml2rfc.XmlRfcParser(None, options=self.options)
        self.options.toc_depth = "1"
        text = self.process()
        parser.text = text.encode('utf8')
        xmlrfc = parser.parse(remove_comments=False, quiet=True, add_xmlns=True)
        preptool = xml2rfc.PrepToolWriter(xmlrfc, options=self.options, date=self.options.date, liberal=True, keep_pis=[xml2rfc.V3_PI_TARGET])
        xmlrfc.tree = preptool.prep()
        if xmlrfc.tree:
            self.options.pagination = False
            writer = xml2rfc.TextWriter(xmlrfc, options=self.options, date=self.options.date)
            text = writer.process()

        if writer.errors:
            raise base.RfcWriterError("Cannot show manpage due to errors.")
        else:
            pydoc.pager(text.lstrip())

    def write(self, filename):
        self.process()

        with open(filename, "w") as file:
            file.write(self.rendered)

        if not self.options.quiet:
            self.log(' Created file %s' % filename)


class RelaxNGCompactRenderer():
    "Simple (and incomplete) converter from an RNG tree to RNC text; enough for our purpose."
    #
    keywords = ['attribute', 'default', 'datatypes', 'div', 'element', 'empty', 'external',
                'grammar', 'include', 'inherit', 'list', 'mixed', 'namespace', 'notAllowed',
                'parent', 'start', 'string', 'text', 'token', ]
    deprecated = base.deprecated_element_tags

    def __init__(self, **kwargs):
        self.nsnames = {}
        if 'deprecated' in kwargs:
            self.deprecated = kwargs.pop('deprecated')
    def render(self, e):
        if e.tag  in [lxml.etree.Comment, ]:
            return ''
        tag = e.tag.replace('{http://relaxng.org/ns/structure/1.0}', '')
        if hasattr(self, tag):
            func = getattr(self, tag)
            return func(e)
        else:
            raise NotImplementedError('%s()' % tag)
    def zeroOrMore(self, e):
        cc = e.getchildren()
        sub = ', '.join(filter(None, [ self.render(c) for c in cc ]))
        sub = '( %s )' % sub if len(cc) > 1 else sub
        return sub + ' *' if sub else ''
    def oneOrMore(self, e):
        cc = e.getchildren()
        sub = ', '.join(filter(None, [ self.render(c) for c in cc ]))
        sub = '( %s )' % sub if len(cc) > 1 else sub
        return sub + ' +' if sub else ''
    def ref(self, e):
        txt = e.get('name')
        if txt in self.deprecated:
            return ''
        if txt in self.keywords:
            txt = r'\%s' % txt
        return txt
    def optional(self, e):
        cc = e.getchildren()
        sub = ', '.join(filter(None, [ self.render(c) for c in cc ]))
        sub = '(%s)' % sub if len(cc) > 1 else sub
        return sub + ' ?' if sub else ''
    def choice(self, e):
        cc = e.getchildren()
        sub = ' | '.join(filter(None, [ self.render(c) for c in cc ]))
        sub = '( %s )' % sub if len(cc) > 1 else sub
        sub = sub.replace(')* | (', ')*\n| (')
        sub = sub.replace(') | (', ')\n| (')
        sub = sub.replace(')+ | (', ')+\n| (')
        return sub
    def interleave(self, e):
        cc = e.getchildren()
        sub = ' & '.join(filter(None, [ self.render(c) for c in cc ]))
        sub = '( %s )' % sub if len(cc) > 1 else sub
        sub = sub.replace(')* & (', ')*\n& (')
        sub = sub.replace(') & (', ')\n& (')
        sub = sub.replace(')+ & (', ')+\n& (')
    def text(self, e):
        return 'text'
    def empty(self, e):
        return 'empty'
    def value(self, e):
        return '"%s"' % e.text
    def grammar(self, e):
        text = '\n'
        self.nsmap = e.nsmap
        for a in e.nsmap.keys():
            v = e.nsmap.get(a)
            self.nsnames[v] = a
            if a:
                text += 'namespace %s = "%s"\n' % (a, v)
        for c in e.getchildren():
            text += self.render(c) + '\n'
        return text
    def define(self, e):
        txt = e.get('name')
        if txt in self.keywords:
            txt = r'\%s' % txt
        cc = e.getchildren()
        sub = ',\n'.join(filter(None, [ self.render(c) for c in cc ]))
        return '%s =\n  %s\n' % (txt, sub)
    def element(self, e):
        name = e.get('name')
        cc = e.getchildren()
        sub = ',\n    '.join(filter(None, [ self.render(c) for c in cc ]))
        txt = 'element %s {\n    %s\n  }\n' % (name, sub)
        txt = re.sub(r'(\n[ \t]*)+\n', '\n', txt)
        return txt
    def attribute(self, e):
        txt = ''
        name = e.get('name')
        nsa = 'http://relaxng.org/ns/compatibility/annotations/1.0'
        default = e.get('{%s}defaultValue' % nsa, None)
        cc = e.getchildren()
        sub = ', '.join(filter(None, [ self.render(c) for c in cc ])) if cc else 'text'
        if len(cc)==1 and re.match(r'\(.*\)$', sub):
            sub = sub[1:-1]
        if default != None:
            txt += '\n    [ %s:defaultValue = "%s" ]\n    ' % (self.nsnames[nsa], default)
        txt += 'attribute %s { %s }' % (name, sub)
        return txt
    def data(self, e):
        type = e.get('type')
        return 'xsd:%s' % type
    def include(self, e):
        return 'include "%s"' % e.get('href').replace('.rng', '.rnc')
    def start(self, e):
        combine = e.get('combine', None)
        if combine == None:
            asg = '='
        elif combine == 'choice':
            asg = '|='
        elif combine == 'interleave':
            asg = '&='
        else:
            raise NotImplementedError('%s' % e)
        cc = e.getchildren()
        sub = ', '.join(filter(None, [ self.render(c) for c in cc ]))
        return 'start %s %s' % (asg, sub)

