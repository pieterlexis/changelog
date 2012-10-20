import re
from sphinx.util.compat import Directive
from docutils.statemachine import StringList
from docutils import nodes
import textwrap
import itertools

def _comma_list(text):
    return re.split(r"\s*,\s*", text.strip())


def _parse_content(content):
    d = {}
    d['text'] = []
    idx = 0
    for line in content:
        idx += 1
        m = re.match(r' *\:(.+?)\: +(.+)', line)
        if m:
            attrname, value = m.group(1, 2)
            d[attrname] = value
        else:
            break
    d["text"] = content[idx:]
    return d


def _ticketurl(ticket):
    return "http://www.sqlalchemy.org/trac/ticket/%s" % ticket

class ChangeLogDirective(Directive):
    has_content = True

    type_ = "change"

    sections = _comma_list("general, orm, orm declarative, orm querying, \
                orm configuration, engine, sql, \
                postgresql, mysql, sqlite")

    subsections = ["feature", "bug", "removed"]

    def run(self):
        ChangeLogDirective._changes = []

        content = _parse_content(self.content)
        version = content.get('version', '')

        p = nodes.paragraph('', '',)
        self.state.nested_parse(self.content[1:], 0, p)

        output = []

        topsection = nodes.section('',
                nodes.title(version, version),
                ids=["changelog-%s" % version]
            )
        if "released" in content:
            topsection.append(nodes.Text("Released: %s" % content['released']))
        else:
            topsection.append(nodes.Text("no release date"))
        output.append(topsection)
        all_section_tags = set(itertools.chain(*[sec.split()
                                    for sec in self.sections]))

        for section in self.sections:
            sec_tags = set(section.split(" "))
            bullets = nodes.bullet_list()
            sec = nodes.section('',
                    nodes.title(section, section),
                    bullets,
                    ids=["%s-%s" % (self.type_, section.replace(" ", "-"))]
            )

            for cat in self.subsections + [""]:
                for rec in self._changes:
                    if rec['type'] == self.type_ and \
                        (
                            rec['tags'].intersection(all_section_tags) == sec_tags
                        ) and \
                        (
                            cat in rec['tags'] or
                            not cat and not rec['tags'].intersection(self.subsections)
                        ):

                        para = rec['node'].deepcopy()

                        insert_ticket = nodes.paragraph('')
                        para.append(insert_ticket)

                        for i, ticket in enumerate(rec['tickets']):
                            if i > 0:
                                insert_ticket.append(nodes.Text(", ", ", "))
                            else:
                                insert_ticket.append(nodes.Text(" ", " "))
                            insert_ticket.append(
                                nodes.reference('', '',
                                    nodes.Text("#%s" % ticket, "#%s" % ticket),
                                    refuri=_ticketurl(ticket)
                                )
                            )

                        tag_node = nodes.strong('',
                                    "[" + cat + "] "
                                )
                        para.children[0].insert(0, tag_node)

                        bullets.append(
                            nodes.list_item('',
                                nodes.target('', '', ids=[rec['id']]),
                                para
                            )
                        )
            if bullets.children:
                topsection.append(sec)

        return output

class ChangeDirective(Directive):
    has_content = True

    def _process_body(self, body):
        return body

    type_ = "change"

    def run(self):
        env = self.state.document.settings.env
        content = _parse_content(self.content)
        p = nodes.paragraph('', '',)
        rec = {
            'tags': set(_comma_list(content.get('tags', ''))).difference(['']),
            'tickets': set(_comma_list(content.get('tickets', ''))).difference(['']),
            'node': p,
            'id': "changelog-%d" % env.new_serialno('changelog'),
            'type': self.type_,
            "title": content.get("title", None)
        }

        self.state.nested_parse(content['text'], 0, p)
        ChangeLogDirective._changes.append(rec)
        return []

class MigrationLogDirective(ChangeLogDirective):
    type_ = "migration"

    sections = _comma_list("New Features, Behavioral Changes, Removed")

    subsections = _comma_list("general, orm, orm declarative, orm querying, \
                orm configuration, engine, sql, \
                postgresql, mysql, sqlite")

    def run(self):
        ChangeLogDirective._changes = []

        content = _parse_content(self.content)
        version = content.get('version', '')

        p = nodes.paragraph('', '',)
        self.state.nested_parse(self.content[1:], 0, p)

        output = []

        title = "What's new in %s?" % version
        topsection = nodes.section('',
                nodes.title(title, title),
                ids=["%s-%s" % (self.type_, version)]
            )
        if "released" in content:
            topsection.append(nodes.Text("Released: %s" % content['released']))

        output.append(topsection)

        for section in self.sections:
            sec = nodes.section('',
                    nodes.title(section, section),
                    ids=["%s-%s" % (self.type_, section.replace(" ", "-"))]
            )

            for cat in self.subsections + [""]:
                for rec in self._changes:
                    if rec['type'] == self.type_ and \
                        (
                            section in rec['tags']
                        ) and \
                        (
                            cat in rec['tags'] or
                            not cat and not rec['tags'].intersection(self.subsections)
                        ):

                        para = rec['node'].deepcopy()

                        insert_ticket = nodes.paragraph('')
                        para.append(insert_ticket)

                        for i, ticket in enumerate(rec['tickets']):
                            if i > 0:
                                insert_ticket.append(nodes.Text(", ", ", "))
                            else:
                                insert_ticket.append(nodes.Text(" ", " "))
                            insert_ticket.append(
                                nodes.reference('', '',
                                    nodes.Text("#%s" % ticket, "#%s" % ticket),
                                    refuri=_ticketurl(ticket)
                                )
                            )


                        sec.append(
                            nodes.section('',
                                nodes.title(rec['title'], rec['title']),
                                para,
                                ids=[rec['id']]
                            )
                        )
            if sec.children:
                topsection.append(sec)

        return output

class MigrationDirective(ChangeDirective):
    type_ = "migration"


def _rst2sphinx(text):
    return StringList(
        [line.strip() for line in textwrap.dedent(text).split("\n")]
    )

def setup(app):
    app.add_directive('changelog', ChangeLogDirective)
    app.add_directive('migrationlog', MigrationLogDirective)
    app.add_directive('migration', MigrationDirective)
    app.add_directive('change', ChangeDirective)

