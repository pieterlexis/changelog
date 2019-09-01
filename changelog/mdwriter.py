import io

from docutils import nodes
from docutils import writers
from docutils.core import publish_string

from .docutils import setup_docutils
from .environment import DefaultEnvironment
from .environment import Environment


class Writer(writers.Writer):

    supported = ("markdown",)

    def __init__(self, limit_version=None, receive_sections=None):
        super(Writer, self).__init__()
        self.limit_version = limit_version
        self.receive_sections = receive_sections

    def translate(self):
        translator = MarkdownTranslator(
            self.document, self.limit_version, self.receive_sections
        )
        self.document.walkabout(translator)
        self.output = translator.output_buf.getvalue()


class MarkdownTranslator(nodes.NodeVisitor):
    def __init__(self, document, limit_version, receive_sections):
        super(MarkdownTranslator, self).__init__(document)
        self.buf = self.output_buf = io.StringIO()
        self.limit_version = limit_version
        self.receive_sections = receive_sections
        self.section = 1
        self.stack = []

        assert not (
            self.limit_version and self.receive_sections
        ), "limit_version and receive_sections are mutually exclusive"

        if self.limit_version or self.receive_sections:
            self.disable_writing()

    def enable_writing(self):
        self.buf = self.output_buf

    def disable_writing(self):
        self.buf = io.StringIO()

    def visit_document(self, node):
        self.document = node
        self.env = Environment.from_document_settings(self.document.settings)

    def visit_section(self, node):
        if (
            self.limit_version
            and node.attributes.get("version_string", "") == self.limit_version
        ):
            self.enable_writing()
            self.section = 1
        elif self.receive_sections and "version_string" in node.attributes:
            self.buf = io.StringIO()
            self.section = 1
        else:
            self.section += 1

    def depart_section(self, node):
        if (
            self.limit_version
            and node.attributes.get("version_string", "") == self.limit_version
        ):
            self.disable_writing()
        elif self.receive_sections and "version_string" in node.attributes:
            self.receive_sections(
                node.attributes["version_string"], self.buf.getvalue()
            )
            self.disable_writing()

        self.section -= 1

    def visit_strong(self, node):
        self.buf.write("**")

    def depart_strong(self, node):
        self.buf.write("**")

    def visit_emphasis(self, node):
        self.buf.write("*")

    def depart_emphasis(self, node):
        self.buf.write("*")

    def visit_literal(self, node):
        self.buf.write("`")

    def visit_Text(self, node):
        self.buf.write(node.astext())

    def depart_Text(self, node):
        pass

    def depart_paragraph(self, node):
        self.buf.write("\n\n")

    def depart_literal(self, node):
        self.buf.write("`")

    def visit_title(self, node):
        self.buf.write("\n%s %s\n\n" % ("#" * self.section, node.astext()))
        raise nodes.SkipNode()

    def visit_changeset_link(self, node):
        # it would be nice to have an absolutely link to the HTML
        # hosted changelog but this requires being able to generate
        # the absolute link from the document filename and all that.
        # it can perhaps be sent on the commandline
        raise nodes.SkipNode()

    def depart_changeset_link(self, node):
        pass

    def visit_reference(self, node):
        if "changelog-reference" in node.attributes["classes"]:
            self.visit_changeset_link(node)
        else:
            self.buf.write("[")

    def depart_reference(self, node):
        if "changelog-reference" in node.attributes["classes"]:
            self.depart_changeset_link(node)
        else:
            self.buf.write("](%s)" % node.attributes["refuri"])

    def visit_admonition(self, node):
        # "seealsos" typically have internal sphinx references so at the
        # moment we're not prepared to look those up, future version can
        # perhaps use sphinx object lookup
        raise nodes.SkipNode()

    def visit_list_item(self, node):
        self.stack.append(self.buf)
        self.buf = io.StringIO()

    def depart_list_item(self, node):
        popped = self.buf
        self.buf = self.stack.pop(-1)

        indent_level = len(self.stack)
        indent_string = " " * 4 * indent_level

        value = popped.getvalue().strip()

        lines = value.split("\n")
        self.buf.write("\n" + indent_string + "-   ")
        line = lines.pop(0)
        self.buf.write(line + "\n")
        for line in lines:
            self.buf.write(indent_string + "    " + line + "\n")

    def _visit_generic_node(self, node):
        pass

    def __getattr__(self, name):
        if not name.startswith("_"):
            return self._visit_generic_node
        else:
            raise AttributeError(name)


def stream_changelog_sections(
    target_filename, config_filename, receive_sections
):
    """Send individual changelog sections to a callable, one per version.

    The callable accepts two arguments, the string version number of the
    changelog section, and the markdown-formatted content of the changelog
    section.

    Used for APIs that receive changelog sections per version.

    """
    Environment.register(DefaultEnvironment)

    setup_docutils()
    with open(target_filename, encoding="utf-8") as handle:
        publish_string(
            handle.read(),
            source_path=target_filename,
            writer=Writer(receive_sections=receive_sections),
            settings_overrides={
                "changelog_env": DefaultEnvironment(config_filename),
                "report_level": 3,
            },
        )
