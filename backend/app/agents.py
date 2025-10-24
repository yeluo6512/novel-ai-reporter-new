from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import Optional, Union

PathLike = Union[str, Path]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AGENTS_FILENAME = "agents.md"
DEFAULT_AGENTS_PATH = PROJECT_ROOT / DEFAULT_AGENTS_FILENAME
DEFAULT_AGENTS_VERSION = "1.0.0"

DEFAULT_AGENTS_TEMPLATE = (
    dedent(
        f"""\
        # Agents 配置示例

        本文件用于定义协作智能体团队，替换示例内容即可生效。

        ## 元数据

        - 版本: {DEFAULT_AGENTS_VERSION}
        - 文件格式: Markdown + YAML

        ## 示例配置

        ```yaml
        version: {DEFAULT_AGENTS_VERSION}
        agents:
          - id: example-reviewer
            name: 示例审查者
            description: 负责审查任务并输出改进建议
            llm:
              provider: openai
              model: gpt-4
            tools:
              - name: repository_reader
                mode: read-only
          - id: example-runner
            name: 示例执行者
            description: 根据建议实施代码变更
            llm:
              provider: openai
              model: gpt-4
            tools:
              - name: repository_writer
                mode: read-write
        merge_strategy:
          name: sequential-proposal
          description: >
            先由审查者生成合并建议，再由执行者评估并最终提交。
          steps:
            - agent: example-reviewer
              output: 审查总结和风险提示
            - agent: example-runner
              output: 最终合并方案和执行计划
        ```

        ## 合并策略示例

        1. 审查者 `example-reviewer` 汇总当前提案并生成合并策略。
        2. 执行者 `example-runner` 复核提案，补充必要的执行细节。
        3. 团队根据执行者输出决定是否自动合并或交由人工确认。
        """
    ).strip()
    + "\n"
)

__all__ = [
    "DEFAULT_AGENTS_FILENAME",
    "DEFAULT_AGENTS_PATH",
    "DEFAULT_AGENTS_TEMPLATE",
    "DEFAULT_AGENTS_VERSION",
    "ensure_agents_file_exists",
    "load_agents_document",
]


def _resolve_target(path: Optional[PathLike]) -> Path:
    if path is None:
        return DEFAULT_AGENTS_PATH

    return Path(path)


def ensure_agents_file_exists(
    path: Optional[PathLike] = None,
    *,
    template: str = DEFAULT_AGENTS_TEMPLATE,
) -> Path:
    """Ensure the agents.md file exists, generating a default template if necessary."""

    target_path = _resolve_target(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if not target_path.exists():
        target_path.write_text(template, encoding="utf-8")

    return target_path


def load_agents_document(path: Optional[PathLike] = None) -> str:
    """Load the agents.md document from disk, regenerating a default file if missing."""

    target_path = ensure_agents_file_exists(path=path)
    return target_path.read_text(encoding="utf-8")
