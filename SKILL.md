---
name: android-app-zero-to-one
description: 把一个模糊想法变成可安装 APK 的完整流程。This skill should be used when the user describes an app idea and wants it actually built ("帮我做一个 XX 应用" / "我要一个能 XX 的 APK" / "仿照 XX 做一个")，或需要从零创建、改造、重新打包任意 Android 应用。覆盖需求澄清、技术选型、骨架搭建、编码实现、命令行构建（无需 Android Studio 与 Gradle）、签名验证到交付的全过程，适用于手机、平板、电视、盒子等各类 Android 设备形态。
agent_created: true
---

# 安卓应用从 0 到 1

## Overview

把"我想要一个能做 XX 的 App"变成手里一个装得上、跑得起来的 APK。
不依赖 Android Studio 和 Gradle，用 JDK + Android SDK 命令行工具直接从源码构建签名包。

核心价值在于**过程**：先想清楚要什么，再动手，最后验证交付。构建链只是其中一步。

## 工作流

### 阶段 0 · 先想清楚，再写代码

拿到想法后**先把关键问题一次性问清楚**（不要挤牙膏式追问）。缺的信息用合理默认值补上，
并明确告知用户用了什么默认值：

| 要确认的事 | 为什么重要 | 常用默认 |
|---|---|---|
| 跑在什么设备上 | 决定 manifest 声明、交互方式、minSdk | 手机 |
| 最低系统版本 | 决定能用哪些 API 和资源类型 | 21（覆盖绝大多数在用设备） |
| 核心功能一句话是什么 | 圈定范围，防止无限发散 | 用户描述的第一句 |
| 要不要联网 / 要哪些权限 | 权限必须在 manifest 声明，运行时还要授权 | 能不要就不要 |
| 数据存哪 | 轻量用 SharedPreferences，结构化用 SQLite | SharedPreferences |
| UI 风格 | 有参照物（"仿 XX"）最好办 | 系统默认深色 |
| 是不是系统级应用 | 桌面、输入法等需要特殊 intent-filter | 普通应用 |
| 用哪把签名证书 | 换证书 = 用户无法覆盖升级 | 复用已有个人证书 |

产出：不超过 10 行的需求摘要，含"做什么 / 不做什么"。

### 仿作模式 · 照着现有 App / 安装包 / 截图做一个

当用户说"做一个像 XX / 仿 XX"，**或上传了一个 apk / exe / 截图**，**或用文字描述想要的功能**时，进入仿作模式。

核心原则：**先模仿其"形"（界面、图标、入口 Activity、布局），功能（必做 / 可选 / 不做）由开发者自己想，或你帮它大致推测里面有什么，再让开发者拍板。** 仿作是"做出同等体验的最小实现"，不是逐像素复刻。

参照物有五种形态，取"形"的方式不同：

| 参照物 | 怎么"模仿其形" | 功能从哪来 |
|---|---|---|
| 一个 App 名（"像 XX"） | 让开发者描述，或你按常识给 UI 草图 | 开发者定 / 你推测 |
| 上传的 **apk** | 用工具链 `aapt2 dump badging` 取包名、入口 Activity、权限、特性、图标；看 res 布局与 strings | 从权限 / Activity / 字符串**推测**，开发者确认 |
| 上传的 **exe**（跨平台参照其 UI） | 看图标、版本信息、界面截图，把 Windows 软件的形态搬到 Android | 从界面与同类 App 推测，开发者确认 |
| 上传的**截图** | 直接照布局 / 配色 / 控件复刻界面 | 开发者定 / 你推测 |
| 用户**文字描述的功能**（"要一个能 XX 的"） | 功能已由用户给出，形由你给 UI 草图或参照同类软件 | 功能已由用户描述，你来落地 |

仍要一次性追问的功能清单（分三档，防发散）：

| 要追问的功能点 | 目的 |
|---|---|
| 参照物是 App 名 / apk / exe / 截图 / 文字描述？ | 决定上面怎么取"形" |
| 你最在意它的哪一点？ | 抓住"灵魂"，别被表面 UI 带偏 |
| **必做**的核心功能（逐条列出） | 圈定 MVP，第一版只做这些 |
| 可以**砍掉 / 简化**的功能 | 先做最小可用，后续再迭代 |
| 目标设备形态（手机 / 电视 / 平板 / 盒子） | 复用上面"设备形态"与 `references/device-variants.md` |
| 有没有界面参考（截图 / 描述 / 配色） | 减少来回确认 |
| 数据从哪来？要不要**兼容原 App 的数据 / 文件格式**？ | 决定是否要解析旧数据库 / SharedPreferences / 私有文件 |
| 要哪些权限、要不要联网 | 权限必须在 manifest 声明，运行时还要授权 |
| 用哪把签名证书 | 复用你的个人证书，否则无法覆盖升级 |

产出：界面草图 / 清单（形）+「功能清单（必做 / 可选 / 不做）」+ 一句话定位 + 目标设备形态，再进入阶段 1 选型。

> 从安装包推测功能的线索：apk 权限 `CAMERA`→拍照、`INTERNET`→联网、`READ_CONTACTS`→通讯录、`WRITE_EXTERNAL_STORAGE`→文件操作；入口 Activity 数量暗示有几个页面。推测只是辅助，最终由开发者确认。
> 详见 `references/replicate-app.md`（含"从安装包 / 截图仿作"的具体步骤与示例）。

### 阶段 1 · 选型

| 决策点 | 选择 | 判据 |
|---|---|---|
| 语言 | Java（默认） | 命令行链对 Java 最顺；Kotlin 需额外编译器 |
| 构建 | 命令行工具链（默认） | 小应用、无第三方依赖、追求快 |
| 构建 | Gradle | 需要第三方库、Jetpack、Compose 时 |
| minSdk | 见 `references/device-variants.md` | 按目标设备定 |

**默认走命令行链**：几十 KB 的小应用几秒出包，不联网下依赖。只有确实需要第三方库时才引入 Gradle。

### 阶段 2 · 起骨架

直接复制 `assets/starter-project/`（已验证可编译）：

```
AndroidManifest.xml
java/<package>/MainActivity.java
res/layout/activity_main.xml
res/values/strings.xml
res/values/styles.xml
res/drawable/ic_launcher.xml
```

然后改包名、改 manifest、加权限、加界面。

### 阶段 3 · 实现

顺序：先 manifest（权限、Activity、intent-filter）→ 再资源（布局、样式、图标）→ 最后 Java 逻辑。
manifest 写错会让后面每一步莫名其妙失败，所以放最前面。

拆分原则：一个功能一个类，不要把几百行塞进 MainActivity。

### 准备工具链（新机器一次性）

目标机器上没有 JDK / Android SDK 时，先跑自动部署，**不需要 Android Studio、不需要 Gradle、不需要管理员权限**：

```bash
python scripts/setup_toolchain.py                      # 装到 ~/.android-zero-to-one
python scripts/setup_toolchain.py --dir D:\toolchain   # 指定位置
python scripts/setup_toolchain.py --mirror cn          # 国内走清华镜像下 JDK
python scripts/setup_toolchain.py --proxy http://127.0.0.1:7890   # 需要代理时
```

它会：下载 Temurin JDK 17 → 下载 Android command-line tools → 用 sdkmanager 装
`platform-tools` / `build-tools;34.0.0` / `platforms;android-34` → 自动接受许可 →
写出 `<root>/toolchain.json`。

之后 `build_apk.py` 会**自动读取**这个配置，无需任何参数。
已有 JDK 时用 `--jdk <path>` 复用，避免重复下载。

### 个人签名证书（每人一次，务必先做）

Android 靠签名判定"这是同一个应用的新版本"。**每个人必须有自己的一把证书**：

- 本技能**不附带任何共享证书** —— 所有人共用一把等于谁都能冒充谁发布
- 一人一把，签你做的**所有**应用，这样新版本才能覆盖安装、保住数据
- 证书丢了，旧版本就再也升不了级（用户必须先卸载）

```bash
python scripts/setup_keystore.py --name "Your Name"    # 生成 ~/.android-zero-to-one/certs/
python scripts/setup_keystore.py --dir D:\toolchain --name "Li" --org "Li Studio"
```

产出两个文件，**必须一起备份**：`personal.jks`（身份）和 `keystore.properties`
（随机密码，权限设为仅本人可读）。两者缺一都解不开。

之后 `build_apk.py` 会**自动找到并用它签名**；万一还没建，构建时会自动建一把再继续。

只有用户在做纯本地一次性验证、且明确不要留身份时，才用 `--no-sign`。
若退化为临时 `debug.jks`，脚本会打 WARNING：这种包将来无法升级。

### 阶段 4 · 构建

**用脚本，不要手写 bat**（bat 有两个静默失败的坑）：

```bash
python scripts/build_apk.py --src <project-dir> --min-sdk 21 --out app.apk
```

| 参数 | 说明 |
|---|---|
| `--min-sdk` | 最低系统版本，按目标设备定（默认 21） |
| `--target-sdk` | 默认 34，需对应 `platforms\android-<n>\android.jar` |
| `--ks / --alias / --storepass` | 覆盖默认的那把个人证书 |
| `--no-keystore-setup` | 没有个人证书时不要自动创建 |
| `--no-sign` | 只打包不签名 |
| `--clean` | 清空中间目录 |

签名完成后脚本**自动跑一次 `apksigner verify`**，签名有问题会直接判失败，不会交出一个坏包。

七步流水线与工具职责见 `references/build-chain.md`。

### 阶段 5 · 验证

```bash
JAVA_HOME=<jdk> apksigner.bat verify --print-certs app.apk   # 成功时几乎不输出
aapt2.exe dump badging app.apk                                # 确认版本、入口、特性
adb install -r -t -d app.apk                                  # 设备验证
```

不能只信"构建成功"。至少确认三件事：签名通过、入口 Activity 正确、minSdk 符合预期。

改完代码重新出包时，再核对一次证书指纹 —— 两次应该**完全相同**：

```bash
apksigner.bat verify --print-certs app.apk | grep -i "SHA-256"
```

指纹变了说明换证书了，用户将无法覆盖安装，必须停下来查清楚。

### 阶段 6 · 交付

- 删掉签名副产物 `app.apk.idsig`
- 放到用户能找到的位置，文件名带用途和版本
- 给出安装命令和验证方法
- 首次交付时提醒用户：`certs/` 下两个文件一起备份，别提交进仓库也别分发给别人

## 设备形态差异（按需查阅）

不同形态的差别主要在 manifest 声明和交互方式，**构建流程完全一样**。
做手机应用就跳过这一节；只有目标是电视 / 盒子 / 平板 / 穿戴时，才查
`references/device-variants.md`。

## 必读：踩过的坑

`references/pitfalls.md` 按"会卡多久"排序，动手前扫一眼，尤其前两条：

1. bat 里调 `d8.bat` / `apksigner.bat` 必须加 `call`，否则**静默失败却返回成功码**
2. bat 文件必须纯 ASCII，中文注释会被 GBK 切碎整行

## 资源

- `scripts/setup_toolchain.py` — 自动部署 JDK + Android SDK（空机器一键可用）
- `scripts/setup_keystore.py` — 生成个人签名证书（每人一把，不共享）
- `scripts/build_apk.py` — 七步构建器，自动处理 .bat 调用、dex 注入、对齐、签名、验签
- `references/build-chain.md` — 工具清单、各步输入输出、常用命令
- `references/pitfalls.md` — 按卡壳时长排序的实战坑
- `references/device-variants.md` — 各设备形态的 manifest 差异（按需查阅）
- `references/replicate-app.md` — 仿作模式：功能追问模板 + 示例
- `assets/starter-project/` — 最小可编译骨架
