#! coding: utf-8


import re
from sphinx.util.compat import Directive
from docutils.statemachine import StringList
from docutils import nodes
from sphinx.util.console import bold
import os
from sphinx.util.osutil import copyfile
import textwrap
import itertools
import collections
import sys

py2k = sys.version_info < (3, 0)
if py2k:
    import md5
else:
    import hashlib as md5


def _is_html(app):
    return app.builder.name in ('html', 'readthedocs')


def _comma_list(text):
    return re.split(r"\s*,\s*", text.strip())


def _parse_content(content):
    d = {}
    d['text'] = []
    idx = 0
    for line in content:
        idx += 1
        m = re.match(r' *\:(.+?)\:(?: +(.+))?', line)
        if m:
            attrname, value = m.group(1, 2)
            d[attrname] = value or ''
        elif idx == 1 and line:
            # accomodate a unique value on the edge of .. change::
            continue
        else:
            break
    d["text"] = content[idx:]
    return d


class EnvDirective(object):
    @property
    def env(self):
        return self.state.document.settings.env

    @classmethod
    def get_changes_list(cls, env):
        if 'ChangeLogDirective_changes' not in env.temp_data:
            env.temp_data['ChangeLogDirective_changes'] = []
        return env.temp_data['ChangeLogDirective_changes']


class ChangeLogDirective(EnvDirective, Directive):
    has_content = True

    default_section = 'misc'

    def run(self):
        self._parse()

        if not ChangeLogImportDirective.in_include_directive(self.env):
            return self._generate_output()
        else:
            return []

    def _parse(self):
        self.sections = self.env.config.changelog_sections
        self.inner_tag_sort = self.env.config.changelog_inner_tag_sort + [""]
        self._parsed_content = _parse_content(self.content)
        self.version = version = self._parsed_content.get('version', '')
        self.env.temp_data['ChangeLogDirective_version'] = version

        p = nodes.paragraph('', '',)
        self.state.nested_parse(self.content[1:], 0, p)

    def _generate_output(self):
        changes = self.get_changes_list(self.env)
        output = []

        id_prefix = "change-%s" % (self.version, )
        topsection = self._run_top(id_prefix)
        output.append(topsection)

        bysection, all_sections = self._organize_by_section(changes)

        counter = itertools.count()

        sections_to_render = [s for s in self.sections if s in all_sections]
        if not sections_to_render:
            for cat in self.inner_tag_sort:
                append_sec = self._append_node()

                for rec in bysection[(self.default_section, cat)]:
                    rec["id"] = "%s-%s" % (id_prefix, next(counter))

                    self._render_rec(rec, None, cat, append_sec)

                if append_sec.children:
                    topsection.append(append_sec)
        else:
            for section in sections_to_render + [self.default_section]:
                sec = nodes.section(
                    '',
                    nodes.title(section, section),
                    ids=["%s-%s" % (id_prefix, section.replace(" ", "-"))]
                )

                append_sec = self._append_node()
                sec.append(append_sec)

                for cat in self.inner_tag_sort:
                    for rec in bysection[(section, cat)]:
                        rec["id"] = "%s-%s" % (id_prefix, next(counter))
                        self._render_rec(rec, section, cat, append_sec)

                if append_sec.children:
                    topsection.append(sec)

        return output

    def _organize_by_section(self, changes):
        compound_sections = [
            (s, s.split(" ")) for s in self.sections if " " in s]

        bysection = collections.defaultdict(list)
        all_sections = set()
        for rec in changes:
            if self.version not in rec['versions']:
                continue
            inner_tag = rec['tags'].intersection(self.inner_tag_sort)
            if inner_tag:
                inner_tag = inner_tag.pop()
            else:
                inner_tag = ""

            for compound, comp_words in compound_sections:
                if rec['tags'].issuperset(comp_words):
                    bysection[(compound, inner_tag)].append(rec)
                    all_sections.add(compound)
                    break
            else:
                intersect = rec['tags'].intersection(self.sections)
                if intersect:
                    for sec in rec['sorted_tags']:
                        if sec in intersect:
                            bysection[(sec, inner_tag)].append(rec)
                            all_sections.add(sec)
                            break
                else:
                    bysection[(self.default_section, inner_tag)].append(rec)
        return bysection, all_sections

    def _append_node(self):
        return nodes.bullet_list()

    def _run_top(self, id_prefix):
        version = self._parsed_content.get('version', '')
        topsection = nodes.section(
            '',
            nodes.title(version, version),
            ids=[id_prefix]
        )

        if self._parsed_content.get("released"):
            topsection.append(
                nodes.Text("Released: %s" %
                           self._parsed_content['released'])
            )
        else:
            topsection.append(nodes.Text("no release date"))

        intro_para = nodes.paragraph('', '')
        len_ = -1
        for len_, text in enumerate(self._parsed_content['text']):
            if ".. change::" in text:
                break

        # if encountered any text elements that didn't start with
        # ".. change::", those become the intro
        if len_ > 0:
            self.state.nested_parse(
                self._parsed_content['text'][0:len_], 0,
                intro_para)
            topsection.append(intro_para)

        return topsection

    def _render_rec(self, rec, section, cat, append_sec):
        para = rec['node'].deepcopy()

        text = _text_rawsource_from_node(para)

        to_hash = "%s %s" % (self.version, text[0:100])
        targetid = "change-%s" % (
            md5.md5(to_hash.encode('ascii', 'ignore')).hexdigest())
        targetnode = nodes.target('', '', ids=[targetid])
        para.insert(0, targetnode)
        permalink = nodes.reference(
            '', '',
            nodes.Text(u"¶", u"¶"),
            refid=targetid,
            classes=['changeset-link', 'headerlink'],
        )
        para.append(permalink)

        if len(rec['versions']) > 1:

            backported_changes = rec['sorted_versions'][
                rec['sorted_versions'].index(self.version) + 1:]
            if backported_changes:
                backported = nodes.paragraph('')
                backported.append(nodes.Text("This change is also ", ""))
                backported.append(nodes.strong("", "backported"))
                backported.append(
                    nodes.Text(" to: %s" % ", ".join(backported_changes), ""))
                para.append(backported)

        insert_ticket = nodes.paragraph('')
        para.append(insert_ticket)

        i = 0
        for collection, render, prefix in (
                (rec['tickets'],
                 self.env.config.changelog_render_ticket, "#%s"),
                (rec['pullreq'],
                 self.env.config.changelog_render_pullreq,
                 "pull request %s"),
                (rec['changeset'],
                 self.env.config.changelog_render_changeset, "r%s"),
        ):
            for refname in collection:
                if i > 0:
                    insert_ticket.append(nodes.Text(", ", ", "))
                else:
                    insert_ticket.append(nodes.Text("References: """))
                i += 1
                if render is not None:
                    if isinstance(render, dict):
                        if ":" in refname:
                            typ, refval = refname.split(":")
                        else:
                            typ = "default"
                            refval = refname
                        refuri = render[typ] % refval
                    else:
                        refuri = render % refname
                    node = nodes.reference(
                        '', '',
                        nodes.Text(prefix % refname, prefix % refname),
                        refuri=refuri
                    )
                else:
                    node = nodes.Text(prefix % refname, prefix % refname)
                insert_ticket.append(node)

        if rec['tags']:
            tag_node = nodes.strong(
                '',
                " ".join(
                    "[%s]" % t for t in
                    [t1 for t1 in [section, cat] if t1 in rec['tags']] +
                    list(rec['tags'].difference([section, cat]))
                ) + " "
            )
            para.children[0].insert(0, tag_node)

        append_sec.append(
            nodes.list_item(
                '',
                nodes.target('', '', ids=[rec['id']]),
                para
            )
        )


class ChangeLogImportDirective(EnvDirective, Directive):
    has_content = True

    @classmethod
    def in_include_directive(cls, env):
        return 'ChangeLogDirective_includes' in env.temp_data

    def run(self):
        # tell ChangeLogDirective we're here, also prevent
        # nested .. include calls
        if self.in_include_directive(self.env):
            self.env.temp_data['ChangeLogDirective_includes'] = True
            p = nodes.paragraph('', '',)
            self.state.nested_parse(self.content, 0, p)
            del self.env.temp_data['ChangeLogDirective_includes']

        return []


class ChangeDirective(EnvDirective, Directive):
    has_content = True

    def run(self):
        content = _parse_content(self.content)
        p = nodes.paragraph('', '',)
        sorted_tags = _comma_list(content.get('tags', ''))
        declared_version = self.env.temp_data['ChangeLogDirective_version']
        versions = set(
            _comma_list(content.get("versions", ""))).difference(['']).\
            union([declared_version])

        # if we don't refer to any other versions and we're in an include,
        # skip
        if len(versions) == 1 and \
                ChangeLogImportDirective.in_include_directive(self.env):

            return []

        def int_ver(ver):
            out = []
            for dig in ver.split("."):
                try:
                    out.append(int(dig))
                except ValueError:
                    out.append(0)
            return tuple(out)

        rec = {
            'tags': set(sorted_tags).difference(['']),
            'tickets': set(
                _comma_list(content.get('tickets', ''))).difference(['']),
            'pullreq': set(
                _comma_list(content.get('pullreq', ''))).difference(['']),
            'changeset': set(
                _comma_list(content.get('changeset', ''))).difference(['']),
            'node': p,
            'type': "change",
            "title": content.get("title", None),
            'sorted_tags': sorted_tags,
            "versions": versions,
            "sorted_versions": list(reversed(sorted(versions, key=int_ver)))
        }

        self.state.nested_parse(content['text'], 0, p)
        ChangeLogDirective.get_changes_list(self.env).append(rec)

        return []


def _text_rawsource_from_node(node):
    src = []
    stack = [node]
    while stack:
        n = stack.pop(0)
        if isinstance(n, nodes.Text):
            src.append(n.rawsource)
        stack.extend(n.children)
    return "".join(src)


def _rst2sphinx(text):
    return StringList(
        [line.strip() for line in textwrap.dedent(text).split("\n")]
    )


def make_ticket_link(
        name, rawtext, text, lineno, inliner,
        options={}, content=[]):
    env = inliner.document.settings.env
    render_ticket = env.config.changelog_render_ticket or "%s"
    prefix = "#%s"
    if render_ticket:
        ref = render_ticket % text
        node = nodes.reference(rawtext, prefix % text, refuri=ref, **options)
    else:
        node = nodes.Text(prefix % text, prefix % text)
    return [node], []


def add_stylesheet(app):
    app.add_stylesheet('changelog.css')


def copy_stylesheet(app, exception):
    app.info(
        bold('The name of the builder is: %s' % app.builder.name), nonl=True)

    if not _is_html(app) or exception:
        return
    app.info(bold('Copying sphinx_paramlinks stylesheet... '), nonl=True)

    source = os.path.abspath(os.path.dirname(__file__))

    # the '_static' directory name is hardcoded in
    # sphinx.builders.html.StandaloneHTMLBuilder.copy_static_files.
    # would be nice if Sphinx could improve the API here so that we just
    # give it the path to a .css file and it does the right thing.
    dest = os.path.join(app.builder.outdir, '_static', 'changelog.css')
    copyfile(os.path.join(source, "changelog.css"), dest)
    app.info('done')


def setup(app):
    app.add_directive('changelog', ChangeLogDirective)
    app.add_directive('change', ChangeDirective)
    app.add_directive('changelog_imports', ChangeLogImportDirective)
    app.add_config_value("changelog_sections", [], 'env')
    app.add_config_value("changelog_inner_tag_sort", [], 'env')
    app.add_config_value("changelog_render_ticket", None, 'env')
    app.add_config_value("changelog_render_pullreq", None, 'env')
    app.add_config_value("changelog_render_changeset", None, 'env')
    app.connect('builder-inited', add_stylesheet)
    app.connect('build-finished', copy_stylesheet)
    app.add_role('ticket', make_ticket_link)
