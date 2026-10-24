"""Python legível a partir do modelo neutro, sem executar conteúdo do projeto."""

from dataclasses import dataclass, field
from .logic import editable, function_names, validate
from .project import Project


@dataclass
class GeneratedCode:
    """Código e mapa de linhas (fluxo, bloco), com diagnósticos separados."""
    text: str
    lines: dict[tuple[str, str], int] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)


def generate(project: Project, source: str = "") -> GeneratedCode:
    """Gera handlers para o contrato ctx do runtime; não exporta aplicativo.

    A origem de cada instrução fica em lines. Nenhum campo livre vira Python
    sem escape: nomes de variáveis são chaves de dicionário e valores usam repr.
    """
    validate(project)
    result = GeneratedCode("")
    lines = ["# Gerado pelo Makebench. Edite a lógica para alterar este arquivo.",
             "# Funções próprias ficam no arquivo .actions.py do projeto.",
             "# Executado em processo separado ao testar o aplicativo.", ""]
    functions, syntax_error = function_names(source)
    if syntax_error:
        result.diagnostics.append(syntax_error)
    from .source import source_files, ENTRY_FILE
    import ast
    for filename,text in source_files(source).items():
        if filename!=ENTRY_FILE:
            try:ast.parse(text)
            except (SyntaxError,ValueError) as exc:result.diagnostics.append(filename+": "+str(exc))
    if not editable(project):
        result.diagnostics.append("Fluxos reservados de outra versão foram preservados sem conversão.")
    else:
        for index, flow in enumerate(project.workflows, 1):
            flow_id = flow["id"]
            if flow.get('editor')=='nodes':
                from .graph import compile_graph
                graph_lines,origins,diagnostics=compile_graph(flow,index,functions)
                offset=len(lines)
                result.lines.update({(flow_id,node):line+offset for node,line in origins.items()})
                result.diagnostics.extend(diagnostics);lines.extend(graph_lines)
                continue
            if flow.get("body") is None:
                result.diagnostics.extend(f"{flow['name']}: {e}" for e in (flow.get("errors") or ["Complete os blocos."]))
                continue
            def expression(node):
                """Converte uma expressão validada em texto Python escapado."""
                op = node["op"]
                if op == "literal":
                    return repr(node["value"])
                if op == "list":
                    return "[" + ", ".join(expression(item) for item in node["items"]) + "]"
                if op == "variable":
                    return f"{ {'project':'variables','window':'ctx.window_variables','local':'local_variables'}[node.get('scope','project')] }.get({node['name']!r})"
                if op == "read":
                    return f"ctx.read({node['component']!r}, {node['attribute']!r})"
                left, right = expression(node["left"]), expression(node["right"])
                if op == "join":
                    return f"(str({left}) + str({right}))"
                return f"({left} {node['operator']} {right})"

            def emit(text, node=None, indent=1):
                """Acrescenta linha e registra origem das expressões da instrução."""
                if node:
                    def mark(value):
                        """Associa a instrução e seus valores à mesma linha Python."""
                        if isinstance(value, dict) and "op" in value:
                            result.lines[(flow_id, value["id"])] = len(lines) + 1
                            for key, child in value.items():
                                if key not in {"then", "else", "body"}:
                                    mark(child)
                        elif isinstance(value, list):
                            for child in value:
                                mark(child)
                    mark(node)
                lines.append("    " * indent + text)

            def body(items, indent=1):
                """Traduz a sequência preservando ordem, condições e comentários."""
                if not items:
                    emit("pass", indent=indent)
                for node in items:
                    for comment in node.get("comment", "").splitlines():
                        emit("# " + comment, indent=indent)
                    op = node["op"]
                    if op in {"log", "message"}:
                        emit(f"ctx.{op}({expression(node['value'])})", node, indent)
                    elif op.startswith("set_"):
                        emit(f"ctx.{op}({node['component']!r}, {expression(node['value'])})", node, indent)
                    elif op == 'terminal_start':
                        emit(f"ctx.terminal_start({node['component']!r}, {expression(node['program'])}, {expression(node['arguments'])})", node, indent)
                    elif op == 'terminal_send':
                        emit(f"ctx.terminal_send({node['component']!r}, {expression(node['value'])})", node, indent)
                    elif op == 'terminal_stop':
                        emit(f"ctx.terminal_stop({node['component']!r})", node, indent)
                    elif op == "show_page":
                        emit(f"ctx.show_page({node['component']!r})", node, indent)
                    elif op == 'go_state':
                        emit(f"ctx.go_state({node['state']!r})", node, indent)
                    elif op == 'open_window':
                        emit(f"ctx.open_window({node['window']!r}, close_current={node.get('close_current', False)!r})", node, indent)
                    elif op == 'close_window':
                        emit("ctx.close_window()", node, indent)
                    elif op == "assign":
                        emit(f"{ {'project':'variables','window':'ctx.window_variables','local':'local_variables'}[node.get('scope','project')] }[{node['name']!r}] = {expression(node['value'])}", node, indent)
                    elif op == "call":
                        if node["function"] not in functions:
                            result.diagnostics.append(f"{flow['name']}: função ‘{node['function']}’ não encontrada em .actions.py.")
                        emit(f"ctx.call_action({node['function']!r}, {expression(node['value'])})", node, indent)
                    elif op in {"run", "script"}:
                        method, key = ("run", "program") if op == "run" else ("run_script", "source")
                        emit(f"ctx.{method}({expression(node[key])}, {expression(node['arguments'])}, admin={node['admin']!r})", node, indent)
                    elif op == "ask":
                        emit(f"{ {'project':'variables','window':'ctx.window_variables','local':'local_variables'}[node.get('scope','project')] }[{node['name']!r}] = ctx.ask({node['kind']!r}, {expression(node['prompt'])}, {expression(node['options'])})", node, indent)
                    elif op == "confirm":
                        emit(f"ctx.confirm({expression(node['prompt'])})", node, indent)
                    elif op == "if":
                        emit(f"if {expression(node['condition'])}:", node, indent)
                        body(node["then"], indent + 1)
                        if node["else"]:
                            emit("else:", indent=indent); body(node["else"], indent + 1)
                    elif op == "repeat":
                        emit(f"for _ in range(max(0, int({expression(node['count'])}))):", node, indent)
                        body(node["body"], indent + 1)
            lines.extend([f"# {flow['name'].replace(chr(10), ' ').replace(chr(13), ' ')}",
                          f"# Evento: {flow['event']['kind']} em {flow['event']['component']!r}",
                          f"def on_event_{index}(ctx):", "    variables = ctx.variables"])
            def uses_local(value):
                """Detecta dados locais por estrutura, sem examinar texto de literais."""
                if isinstance(value,dict):return value.get('scope')=='local' or any(uses_local(v) for v in value.values())
                if isinstance(value,list):return any(uses_local(v) for v in value)
                return False
            if uses_local(flow['body']):
                emit('local_variables = {}')
            body(flow["body"])
            lines.append("")
    result.text = "\n".join(lines) + "\n"
    return result
