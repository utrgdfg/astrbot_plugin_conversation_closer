# 对话自然收尾 / Conversation Closer

<p align="center">
  <img src="logo.png" width="180" alt="Conversation Closer Logo">
</p>

[![CI](https://github.com/utrgdfg/astrbot_plugin_conversation_closer/actions/workflows/ci.yml/badge.svg)](https://github.com/utrgdfg/astrbot_plugin_conversation_closer/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.24.2%2C%3C5-blue)](https://astrbot.app/)
[![Moe Counter](https://mayu.due.moe/get/@utrgdfg-astrbot_plugin_conversation_closer?theme=booru-lewd)](https://github.com/utrgdfg/astrbot_plugin_conversation_closer)

让已经说完的对话自然停下来，避免 Bot 为了回复而继续回复。

> Conversation Closer 只判断一件事：**当前交流是否已经完成，此时不再回复会不会更自然？**
>
> 它不是随机回复插件，不会按照概率、关键词或“回复欲望”决定沉默。

## 一眼看懂

没有本插件时：

```text
Bot：快点回来。
用户：好。
Bot：知道啦，路上小心。
用户：好。
Bot：那我等你。
```

启用本插件后：

```text
Bot：快点回来。
用户：好。

【对话自然结束，Bot 保持沉默】
```

插件会在 AstrBot 准备调用主聊天模型前，用一个单独的小模型阅读最近几条对话。只有它非常确定交流已经结束时，才会阻止这一次回复。

## 哪些情况会自然结束

下面这些交流已经完成，Bot 通常不需要再补一句：

| Bot | 用户 | 结果 |
| --- | --- | --- |
| 记得早点睡。 | 知道了。 | 自然结束 |
| 你几点回来？ | 大概八点。 | 自然结束 |
| 八点回来可以吗？ | 可以。 | 自然结束 |
| 那先这样。 | 好。 | 自然结束 |
| 晚安。 | 晚安。 | 自然结束 |

如果用户还有问题、补充信息或情绪需要回应，插件会正常放行：

| Bot | 用户 | 结果 |
| --- | --- | --- |
| 记得早点睡。 | 好的，不过我还是睡不着。 | 继续回复 |
| 出去买点吃的。 | 可以，你想吃什么？ | 继续回复 |
| 那就这么做。 | 好的，但第二步怎么做？ | 继续回复 |
| 你想吃什么？ | 不知道。 | 继续回复 |

所以，短消息不等于对话结束，出现“好的”“可以”“谢谢”等词也不会自动触发沉默。

## 快速安装

### 从 GitHub 安装

在 AstrBot WebUI 的插件安装页面中填写：

```text
https://github.com/utrgdfg/astrbot_plugin_conversation_closer
```

### 从插件市场安装

正式上架后，可在 AstrBot 插件市场搜索“对话自然收尾”。

## 首次配置

安装后只需要完成一项必要设置：

1. 打开 Conversation Closer 的插件配置。
2. 在 `Judge Provider` 中选择一个已经配置好的 AstrBot LLM Provider。
3. 保存配置，其他选项先保持默认即可。

推荐选择响应快、价格低、指令遵循稳定的小模型。插件直接使用 AstrBot 中已有的 Provider，不需要额外填写 API Key，也不要求与主聊天模型相同。

默认只对私聊生效，群聊功能默认关闭。

## 常用配置

| 配置项 | 默认值 | 用途 |
| --- | ---: | --- |
| `enabled` | `true` | 插件总开关 |
| `private_enabled` | `true` | 在私聊中启用 |
| `group_enabled` | `false` | 在群聊中启用，当前仍是实验功能 |
| `judge_provider_id` | 未选择 | 用来判断对话是否结束的模型 |
| `history_limit` | `10` | 判断时最多参考多少条最近消息 |
| `confidence_threshold` | `0.85` | 允许结束对话的最低可信度 |
| `judge_timeout_seconds` | `5` | 判断超时后立即恢复正常回复 |
| `debug_log` | `false` | 输出脱敏后的判断日志 |

`confidence_threshold` 不是回复概率。插件没有任何随机沉默机制。

<details>
<summary>查看高级配置</summary>

| 配置项 | 默认值 | 用途 |
| --- | ---: | --- |
| `session_ttl_minutes` | `1440` | 清理长期未使用的会话缓存 |
| `max_message_chars` | `800` | 单条历史消息的最大长度 |
| `max_context_chars` | `6000` | 一次判断所使用上下文的最大总长度 |
| `judge_max_tokens` | `160` | Judge 输出的 Token 上限，部分 Provider 可能忽略 |

</details>

## 管理命令

| 命令 | 作用 |
| --- | --- |
| `/closer status` | 查看插件状态、当前配置和会话历史条数 |
| `/closer clear` | 清空当前会话的内存历史 |
| `/closer test` | 查看当前会话最近一次判断结果 |

这些命令不会被 Conversation Closer 自己拦截。普通聊天中也不会出现调试提示或“对话已结束”之类的消息。

## 判断失败会怎样

插件遵循 **Fail-open（失败时放行）** 原则。

如果 Provider 未配置、请求超时、网络异常、模型报错、输出格式错误，或者插件无法可靠取得上下文，AstrBot 都会继续原来的聊天流程。也就是说：**宁可多回复一句，也不吞掉真正需要回答的消息。**

模型只会返回三种判断：

- `END`：交流已经完成；只有可信度达到阈值时才保持沉默。
- `CONTINUE`：还有内容需要回应，正常交给主聊天模型。
- `UNCERTAIN`：无法确定，按照 `CONTINUE` 处理。

## Token、费用与隐私

每条符合条件的用户消息最多增加一次很小的 LLM 请求，因此会产生少量额外 Token 和费用。

用于判断的最近聊天文本会发送给你自己选择的 Judge Provider。请确认你接受该 Provider 的隐私政策和数据保留规则。

插件本身：

- 不把聊天记录上传到开发者服务器；
- 不包含遥测、广告、统计上报或远程控制；
- 不自行连接额外的 AI 服务；
- 仅在内存中保存有限的最近消息，AstrBot 重启或插件重载后会清空。

默认日志不会记录完整聊天内容、Judge 原因、API Key、Token、Cookie 或 Provider 完整配置。开启 Debug 后也只输出脱敏的判断摘要。

## 工作原理（简版）

1. 收到普通聊天消息后，插件读取当前会话最近几条对话。
2. 独立 Judge Provider 只判断 `END`、`CONTINUE` 或 `UNCERTAIN`，不会替用户生成回复。
3. 只有高可信度 `END` 会调用 `event.stop_event()`，Bot 保持真正的沉默。
4. 其他结果和所有异常都不修改 AstrBot 原有流程。
5. Bot 实际发送成功的内容会通过 AstrBot 官方发送后 Hook 加入会话历史。

同一会话会按顺序处理，不同会话互不阻塞；历史、消息去重记录和会话锁都有数量或时间限制，不会无限增长。

Judge 提示词会把聊天记录当作不可信数据，不执行其中的“忽略提示”“输出 END”等指令。模型输出还会经过严格的 JSON、类型和取值范围检查，但任何 LLM 都无法承诺绝对零误判，因此建议保留默认高阈值。

## 兼容性与限制

- 支持 AstrBot `>=4.24.2,<5`。
- CI 覆盖 Python 3.12、3.13、3.14，并检查 AstrBot `v4.24.2` 与官方主线 API。
- 目前尚未完成真实平台适配器的端到端测试，因此暂不声明特定平台支持范围。
- 群聊中的交流边界更复杂，默认关闭并视为实验功能。
- 第一版不理解图片、语音、视频或文件内容，只记录轻量占位符。
- 会话历史只保存在内存中，不会跨重启保留。
- 不同 Provider 的模型能力不同，实际判断效果可能存在差异。

## 常见问题

### 安装后没有任何变化？

运行 `/closer status`，确认已经选择 Judge Provider。Provider 不可用时，插件会主动放行，所以 Bot 仍会像未安装时一样回复。

### 为什么没有发送“对话已结束”？

沉默就是本插件的功能。再发送一条结束提示，反而会制造新的收尾消息。

### 能把可信度阈值调低吗？

可以，但不建议。阈值越低，误吞需要回复的消息的风险越高。

### 会不会看到“好的”就不回复？

不会。插件根据上下文判断交流是否闭环，不包含关键词停止规则。

## 开发与测试

```bash
python -m pip install -e ".[dev]"
python -m compileall -q .
ruff check .
pytest
bandit -q -r . -x ./tests
```

测试不会调用真实 LLM，也不需要 API Key。回归语料位于 [`tests/cases/conversation_cases.json`](tests/cases/conversation_cases.json)，安全问题请按 [`SECURITY.md`](SECURITY.md) 私下报告。

## 更新与许可证

- 更新记录：[`CHANGELOG.md`](CHANGELOG.md)
- 参与开发：[`CONTRIBUTING.md`](CONTRIBUTING.md)
- 发布检查：[`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md)
- 源代码许可证：[MIT](LICENSE)

本插件为独立实现，没有复制或修改 should-I-respond 类插件代码。`logo.png` 由项目维护者提供，不自动适用源码 MIT 许可证；再分发前请阅读 [`ASSET_LICENSE.md`](ASSET_LICENSE.md)。
