# AI 语音绘图工具
演示视频 

我用夸克网盘给你分享了「演示视频.mp4」，点击链接或复制整段内容，打开「夸克APP」即可获取。
/~634a3Z3bnZ~:/
链接：https://pan.quark.cn/s/0e97f75fe9a7?pwd=WEAD
提取码：WEAD

纯语音控制的桌面绘图应用。用户只能通过语音指令完成绘图创作，不能使用鼠标或键盘。

## 功能

- 语音选择工具（笔/橡皮/线条）
- 语音选择颜色（50+ 中英文颜色名 + HEX）
- 语音绘制形状（圆/矩形/三角形/星形/直线）
- 语音调整笔刷粗细
- 语音撤销/清空
- 语音 AI 生成图片（DALL·E 3）
- 实时语音识别反馈面板
- 命令历史面板

## 技术栈

| 组件 | 选择 |
|---|---|
| 语言 | Python 3.10+ |
| GUI | PyQt6 |
| 语音识别 | OpenAI Whisper (base/small) |
| AI 绘图 | OpenAI DALL·E 3 |
| 麦克风 | sounddevice + numpy |

## 安装

### 1. 安装 Python

确保已安装 **Python 3.10 或更高版本**。

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

如果需要本地 Whisper 模型，还需要安装 Whisper 的 C++ 依赖：
- **Windows**: 确保已安装 Visual C++ Build Tools
- **Linux**: `sudo apt install portaudio19-dev`

### 3. 配置 API Key（AI 生成功能需要）

```bash
# Windows (PowerShell)
$env:OPENAI_API_KEY = "sk-xxxx"

# Windows (CMD)
set OPENAI_API_KEY=sk-xxxx

# Linux / macOS
export OPENAI_API_KEY="sk-xxxx"
```

## 运行

```bash
python main.py
```

## 语音指令

| 指令 | 说明 | 示例 |
|---|---|---|
| 笔/橡皮/线条 | 切换工具 | "用画笔"、"用橡皮" |
| 颜色 | 切换颜色 | "红色"、"蓝色"、"深蓝" |
| 粗/细/大小 | 调整粗细 | "粗的"、"大小 10" |
| 画圆/矩形/三角形/星 | 绘制形状 | "画个圆"、"画个星" |
| 撤销/清空 | 操作 | "撤销"、"清空" |
| 生成 | AI 画图 | "生成一幅日落海景" |
| 开始/停止监听 | 控制麦克风 | "开始监听"、"停止监听" |

## 目录结构

```
AI-voice-to-image/
├── main.py                   # 入口
├── config.py                 # 全局配置
├── requirements.txt          # 依赖
├── 设计文档.md               # 设计文档
├── ui/                       # 界面组件
├── voice/                    # 语音识别
├── parser/                   # 命令解析
├── engine/                   # 绘图引擎
├── ai/                       # AI 服务
└── tests/                    # 测试
```

## 快捷键（紧急备用）

- `Esc` — 停止语音监听
- `Ctrl+Z` — 撤销
