# LSkeleton_QT

## 1. 项目简介
`LSkeleton_QT` 是一个基于 Qt 的 C++ 工程骨架，包含：
- 基础核心能力（日志、配置、事件总线、对象注册、反射）
- 插件管理能力（按配置加载、依赖检查、初始化/清理）
- 通用 UI 组件库（无边框窗口、标题栏、对话框封装）
- WebView 组件（`QWebEngineView` + `QWebChannel`）
- 示例应用与基础测试

该仓库用于快速搭建具备“核心库 + 插件 + UI + WebView”形态的桌面应用。

## 2. 目录结构
```text
code/
├─ cmake/                    # 公共 CMake 宏与 Qt 相关配置
├─ src/
│  ├─ Core/
│  │  ├─ LCommon/            # 通用模板工具（单例、线程池、循环队列等）
│  │  ├─ LBase/              # 基础能力（配置、日志、事件总线、反射、对象注册）
│  │  └─ PluginManager/      # 插件管理器
│  ├─ Lib/
│  │  ├─ LUiCommon/          # 通用 UI 组件
│  │  ├─ LWebView/           # WebView 与 JS 桥接
│  │  └─ LBaseGrap/          # 图结构算法示例
│  ├─ Plugin/                # 示例插件（PluginA / PluginB）
│  ├─ App/                   # 示例应用（App1 / Ui_Test / WebViewTest）
│  ├─ test/                  # QtTest 测试
│  └─ _conf/                 # 配置与资源
└─ CMakeLists.txt            # 顶层构建入口
```

## 3. 构建环境
- OS: Windows（当前工程默认已适配）
- CMake: >= 3.12
- 编译器: MSVC（示例环境为 VS 2026 / MSVC 19.50）
- Qt: Qt5（工程配置基于 Qt5）

### 3.1 Qt 路径
`cmake/module_qt.cmake` 通过环境变量 `QT_DIR` 查找 Qt：
```powershell
$env:QT_DIR = "C:\Qt\5.14.2\msvc2017_64\lib\cmake\Qt5"
```

## 4. 构建步骤
在仓库根目录（`code`）执行：
```powershell
cmake -S . -B build
cmake --build build --config Debug -- /m
```

构建产物默认输出到：
- `bin/`：可执行文件与动态库
- `bin/lib/`：导入库/静态库

## 5. 运行说明
常用可执行文件：
- `bin/App1.exe`
- `bin/Ui_Test.exe`
- `bin/WebViewTest.exe`
- `bin/test.exe`

插件目录默认从可执行目录下 `plugin/` 读取；插件加载顺序与启用状态由配置文件控制。

## 6. 本次代码修复与改进（2026-03）
本次主要面向 `src/` 下代码做了缺陷修复、告警清理和注释增强。

### 6.1 关键缺陷修复
- 修复 `ThreadPool` 析构时“持锁 join”潜在死锁问题。
- 修复 `CircularQueue` 对数组元素手工析构/placement new 的未定义行为风险。
- 重构 `LEventBus`：
  - 增加空指针保护
  - 回调调用前复制订阅列表，避免长时间持锁
  - 增强取消订阅逻辑稳定性
- 重构 `PluginManager`：
  - 修复插件加载失败时 loader 泄漏
  - 修复接口不匹配时仍返回成功的问题
  - 增加循环依赖检测（DFS + visiting 集）
  - 修复重复加载状态污染
  - 优化批量加载/卸载顺序与兜底清理
- 修复 `LDialog` 递归信号连接导致的重入/栈溢出风险。
- 修复 `LWidget`：
  - 构造阶段重复创建标题栏导致泄漏
  - 内容区重复叠加控件风险
  - 屏幕对象空指针访问风险
- 修复 `LWebBrowser`：
  - 去除不可达代码
  - 增加 `view()` 空指针防护
  - 完整实现 `javaScriptPrompt`
- 修复 `LWebView`：
  - 去除不可达返回
  - 修复对象注册检测逻辑
  - 增加 JS 桥接注册/反注册空指针保护
- 修复 `LTitleBar` 最小化按钮图标路径错误（文件名多余空格）。
- 去掉测试主程序中的 `system("pause")`，避免自动化执行卡住。

### 6.2 跨平台与可维护性改进
- 修复多处头文件大小写不一致问题（Windows 不敏感、Linux 敏感）。
- 统一关键头文件编码，消除编译阶段编码告警（`C4828`）。
- `ObjectRegistry` 改为 `QPointer` 持有对象引用，避免悬挂指针。

### 6.3 编译状态
- 当前 `Debug` 全量构建已通过。
- 本次修改后，构建输出中未再出现之前的编码类告警。

## 7. 测试说明
执行：
```powershell
./bin/test.exe
```

说明：测试程序会输出大量日志（日志模块测试会主动打印多级别日志），请结合返回码与 QtTest 输出文件综合判断结果。

## 8. 开发建议
- 新增模块时优先复用 `cmake/module.cmake` 中的 `CreateTarget` 宏。
- 插件应提供稳定的 `name/version/dependencies` 元数据，便于依赖校验。
- 对跨线程组件（事件总线/线程池）建议补充压力测试和竞态测试。
