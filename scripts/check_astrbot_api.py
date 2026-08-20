"""静态检查本插件使用的 AstrBot 源码接口契约。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


class ContractError(RuntimeError):
    """所需的 AstrBot 源码契约不存在时抛出。"""


def parse(path: Path) -> ast.Module:
    if not path.is_file():
        raise ContractError(f"缺少源码文件：{path}")
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def class_node(module: ast.Module, name: str) -> ast.ClassDef:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise ContractError(f"缺少类：{name}")


def method_node(owner: ast.ClassDef, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in owner.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise ContractError(f"缺少方法：{owner.name}.{name}")


def function_names(module: ast.Module) -> set[str]:
    return {
        node.name
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def check(root: Path) -> None:
    config_module = parse(root / "astrbot/core/config/astrbot_config.py")
    astrbot_config = class_node(config_module, "AstrBotConfig")
    schema_parser = method_node(astrbot_config, "_config_schema_to_default_config")
    schema_contract = ast.dump(schema_parser)
    for marker in ("object", "items"):
        if marker not in schema_contract:
            raise ContractError(
                f"AstrBotConfig 分组对象配置契约已变化：{marker}"
            )

    context_module = parse(root / "astrbot/core/star/context.py")
    context = class_node(context_module, "Context")
    llm_generate = method_node(context, "llm_generate")
    if not isinstance(llm_generate, ast.AsyncFunctionDef):
        raise ContractError("Context.llm_generate 不再是异步方法")
    keyword_args = {argument.arg for argument in llm_generate.args.kwonlyargs}
    required_llm_args = {
        "chat_provider_id",
        "prompt",
        "tools",
        "system_prompt",
        "contexts",
    }
    if not required_llm_args <= keyword_args or llm_generate.args.kwarg is None:
        raise ContractError("Context.llm_generate 关键字参数契约已变化")

    event_module = parse(root / "astrbot/core/platform/astr_message_event.py")
    event = class_node(event_module, "AstrMessageEvent")
    required_event_methods = {
        "stop_event",
        "is_private_chat",
        "get_messages",
        "get_message_str",
        "get_session_id",
        "get_group_id",
        "get_extra",
        "set_extra",
        "get_result",
    }
    available_event_methods = {
        node.name
        for node in event.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing_event_methods = required_event_methods - available_event_methods
    if missing_event_methods:
        raise ContractError(f"AstrMessageEvent 方法契约已变化：{missing_event_methods}")

    register_module = parse(root / "astrbot/core/star/register/star_handler.py")
    required_registers = {
        "register_after_message_sent",
        "register_command_group",
        "register_event_message_type",
        "register_on_decorating_result",
    }
    if missing_registers := required_registers - function_names(register_module):
        raise ContractError(f"插件注册接口已变化：{missing_registers}")

    filter_api = (root / "astrbot/api/event/filter/__init__.py").read_text(encoding="utf-8")
    for public_name in (
        "after_message_sent",
        "command_group",
        "event_message_type",
        "on_decorating_result",
    ):
        if public_name not in filter_api:
            raise ContractError(f"事件过滤接口不再公开：{public_name}")

    handler_source = (root / "astrbot/core/star/star_handler.py").read_text(
        encoding="utf-8"
    )
    if 'self._handlers.sort(key=lambda h: -h.extras_configs["priority"])' not in handler_source:
        raise ContractError("处理器优先级降序执行契约已变化")

    waking_source = (root / "astrbot/core/pipeline/waking_check/stage.py").read_text(
        encoding="utf-8"
    )
    for marker in ("activated_handlers", "is_at_or_wake_command"):
        if marker not in waking_source:
            raise ContractError(f"WakingCheck 契约已变化：{marker}")


def main() -> int:
    if len(sys.argv) != 2:
        print("用法：check_astrbot_api.py ASTRBOT源码路径")
        return 2
    root = Path(sys.argv[1]).resolve()
    try:
        check(root)
    except (ContractError, OSError, SyntaxError) as exc:
        print(f"AstrBot 接口契约检查失败：{exc}")
        return 1
    print(f"AstrBot 接口契约检查通过：{root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
