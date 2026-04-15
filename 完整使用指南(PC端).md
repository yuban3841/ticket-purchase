# 大麦网自动抢票系统 - 使用指南（仅移动端）

> 本仓库当前只支持 Android + Appium 移动端抢票。
> PC/Web（Selenium + Chrome）流程已停用，不再维护。

## 重要说明

- 不要再运行 `python damai/damai.py`。
- 不要再使用 Chrome/ChromeDriver 相关检查脚本。
- 唯一可用入口是 `damai_appium/damai_app_v2.py`。

## 一键启动（推荐）

在项目根目录依次执行：

```bash
./check_environment.sh
./start_appium.sh
./start_ticket_grabbing.sh
```

## Windows 启动方式

如果你在 PowerShell 下运行：

```powershell
# 1) 确认设备在线
adb devices -l

# 2) 启动 Appium
npx appium --address 127.0.0.1 --port 4723 --relaxed-security

# 3) 启动抢票脚本
python damai_appium/damai_app_v2.py
```

## 配置文件

编辑 `damai_appium/config.jsonc`：

```json
{
  "server_url": "http://127.0.0.1:4723",
  "device_name": "你的设备序列号",
  "keyword": "演出关键词",
  "users": ["观演人1", "观演人2"],
  "city": "城市",
  "date": "日期",
  "price": "票价文本",
  "price_index": 0,
  "if_commit_order": false
}
```

字段说明：

- `device_name`: 推荐写入 `adb devices -l` 输出的序列号，避免选错设备。
- `price_index`: 票价索引，从 0 开始。
- `if_commit_order`: `false` 为测试模式（到提交前停止），`true` 才会实际提交订单。

## 常见问题

### 1) 点击同意后闪退

- x86 模拟器存在已知兼容问题，建议使用 ARM64 真机或 ARM 兼容实例。

### 2) Appium Settings 初始化失败

- 脚本已内置自动重试兜底。
- 若仍失败，先手动确认设备可正常打开大麦 App。

### 3) 观演人选择失败

- 请确认 `users` 配置和页面显示名字完全一致（空格、后缀、符号都要一致）。

## 当前状态

- Web/PC 端文档已归档，不再作为可执行流程。
- 后续功能和修复将只围绕移动端进行。
