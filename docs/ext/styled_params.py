from docutils import nodes
from docutils.parsers.rst import Directive, directives


class ParameterDirective(Directive):
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = True
    option_spec = {"required": directives.flag, "type": directives.unchanged}

    def run(self):
        param_name = self.arguments[0]
        param_type = self.options.get("type", "str")
        required = "REQUIRED" if "required" in self.options else ""

        container = nodes.container()
        container["classes"].append("patcher-parameter")
        
        header = nodes.container()
        header["classes"].append("patcher-param-header")

        param_name_node = nodes.literal(text=param_name)
        param_name_node["classes"].append("patcher-param-name")

        param_type_node = nodes.emphasis(text=f"({param_type})")
        param_type_node["classes"].append("patcher-param-type")

        required_node = nodes.strong(text=f"{required}")
        required_node["classes"].append("patcher-param-required")

        header += param_name_node
        header += param_type_node
        header += required_node

        description_container = nodes.container()
        description_container["classes"].append("patcher-param-desc")

        self.state.nested_parse(self.content, self.content_offset, description_container)

        # Assembling everything inside the container
        container += header
        container += description_container

        return [container]


def setup(app):
    app.add_directive("param", ParameterDirective)
    app.add_css_file("custom.css")
