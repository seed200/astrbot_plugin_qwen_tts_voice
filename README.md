# Qwen 3 TTS 语音回复

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.24.0-blue)](https://github.com/AstrBotDevs/AstrBot)

用本机 **Qwen 3 TTS** 的 OpenAI 兼容接口做参考音频克隆，每隔 N 条
AstrBot 回复，把文字回复替换成一条 QQ 语音。

- Qwen TTS 地址：`http://127.0.0.1:7860`
- 接口：`POST /v1/audio/speech`
- 克隆方式：`ref_audio` + `ref_text`
- 默认模型：`Qwen/Qwen3-TTS-12Hz-0.6B-Base`
- 适配器：`aiocqhttp`（OneBot v11）

## 功能

- 可配置参考语音目录
- 可配置参考语音文件名
- 可配置参考语音对应文字
- 每隔 N 条回复发一条语音（`0` 表示关闭）
- 可选择语音时是否同时发送文字
- 支持 wav / mp3 输出
- 可配置 TTS 超时、语速、最大文字长度
- 支持可选 API Key

## 前提

### 1. AstrBot

要求 AstrBot `>= 4.24.0`，并已接入 `aiocqhttp` 平台。

### 2. Qwen TTS WebUI 开启 API

Qwen TTS 默认只开 WebUI，需要加 `--api` 才会暴露
`/v1/audio/speech`。启动命令类似：

```bash
python launch.py --api
```

验证：

```text
http://127.0.0.1:7860/docs
http://127.0.0.1:7860/v1/models
```

如果 `/v1/models` 返回 404，说明没有用 `--api` 启动。

## 安装

把整个仓库目录放进 AstrBot 的插件目录：

```text
AstrBot/data/plugins/astrbot_plugin_qwen_tts_voice/
```

重启 AstrBot，或在 WebUI 的插件页面重载插件。

依赖只有 `httpx`，AstrBot 环境通常已经自带；如果缺失：

```bash
pip install httpx
```

## 配置

AstrBot WebUI：

```text
插件 -> Qwen 3 TTS 语音 -> 插件配置
```

主要字段：

| 字段 | 说明 |
| --- | --- |
| `Qwen TTS API 地址` | 默认 `http://127.0.0.1:7860` |
| `API Key` | Qwen TTS 没有设置 API Key 时留空 |
| `TTS 模型` | `0.6B-Base` 更快，`1.7B-Base` 音质更好但更慢 |
| `参考语音存放目录` | 参考音频所在目录的绝对路径 |
| `参考语音文件名` | 目录下的文件名，也可直接填绝对路径 |
| `参考语音对应文字` | 参考音频里实际说的内容，可留空 |
| `每多少条回复发一条语音` | 默认 5；0 关闭 |
| `语音时同时发送文字` | 默认关闭 |
| `音频格式` | `wav` 或 `mp3` |
| `语音最大文字长度` | 超过后保留文字，避免生成过慢 |
| `TTS 超时时间` | 默认 180 秒 |
| `语速` | 默认 1.0 |

## 使用自己的参考音频

1. 准备一段清晰、单人、无背景音乐的参考音频（建议 3～15 秒）
2. 放到一个固定目录，例如：

```text
D:\tts_refs\my_voice.wav
```

3. 在插件配置里填写：
   - 参考语音存放目录：`D:\tts_refs`
   - 参考语音文件名：`my_voice.wav`
   - 参考语音对应文字：这段音频里实际说的话

参考文字越准确，克隆效果通常越好；留空时会只使用说话人特征。

## 计数规则

计数按会话（私聊 / 每个群）分别计算：

- `voice_every_n = 5`：第 5、10、15……条回复发语音
- `voice_every_n = 0`：关闭语音
- 语音合成失败时保留原文字回复
- 文字超过 `max_text_chars` 时保留文字，不强行生成语音

## 常见问题

### Qwen TTS 返回 404

没有用 `--api` 启动，或地址填错。访问
`http://127.0.0.1:7860/v1/models` 检查。

### 语音合成 500 / 卡住

Qwen TTS WebUI 在某些显卡环境下连续第二次生成会触发 CUDA Graph /
显存分配器错误（`CUDACachingAllocator`）。这是 Qwen 服务端问题，
不是本插件逻辑。

插件会对 500 自动重试一次；如果 Qwen 服务端仍然不稳定，建议：

- 更新 Qwen TTS WebUI / PyTorch 版本；
- 或在 Qwen 服务端修复连续生成问题；
- 或降低 `每多少条回复发一条语音` 的频率。

### 语音发不出去

不同 OneBot 适配器对语音格式支持不同。先把「音频格式」改成 `mp3`
再试；仍然不行时检查适配器是否支持 `record` 消息段。

## License

MIT
