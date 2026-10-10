# android-app-zero-to-one

把"我想要一个能做 XX 的 App"变成手里一个装得上、跑得起来的 APK —— 不需要 Android Studio，不需要 Gradle。

适用于手机、平板、电视、盒子等任意 Android 设备形态。

## 这个技能做什么

构建链只是其中一步。真正重要的是过程：**先想清楚要什么，再动手，最后验证交付。**
脚本负责把命令行构建链（aapt2 → javac → d8 → zipalign → apksigner）跑通，
并把工具链和签名证书都做成"空机器一键可用"。

## 快速开始

```bash
# 1. 复制最小骨架
cp -r assets/starter-project myapp

# 2. 准备工具链（空机器第一次，约 2 分钟）
python scripts/setup_toolchain.py            # 装到 ~/.android-zero-to-one
python scripts/setup_toolchain.py --mirror cn   # 国内走清华镜像
python scripts/setup_toolchain.py --proxy http://127.0.0.1:7890

# 3. 生成你的个人签名证书（每人一把，不共享）
python scripts/setup_keystore.py --name "Your Name"

# 4. 构建
python scripts/build_apk.py --src myapp --out myapp.apk
```

## 工具链自动部署

`setup_toolchain.py` 下载 Temurin JDK 17 + Android command-line tools，用 sdkmanager 安装
`platform-tools` / `build-tools;34.0.0` / `platforms;android-34`，写出 `toolchain.json`。
之后 `build_apk.py` **自动读取**，无需任何参数。

支持参数：`--dir <root>` / `--proxy <url>` / `--mirror cn` / `--jdk <已有jdk>` / `--sdk <已有sdk>`。

## 签名

每个开发者必须有自己的一份证书（`scripts/setup_keystore.py` 生成，**本技能不附带任何共享证书**）：

- 证书丢了，你就无法升级自己已发布的应用（用户必须卸载重装）
- 临时 `debug.jks` 签的包将来无法升级，脚本会打 WARNING
- 绝不共享证书：谁拿到 `personal.jks` + `keystore.properties`，谁就能冒充你发布

签名完成后脚本自动跑 `apksigner verify`；改完代码重新构建时，两次证书指纹应完全一致。

## 仿作模式（照着现有 App 做一个）

如果用户说"做一个像 XX 的 App / 仿 XX"，先别照抄界面——按这份清单一次性问清功能边界：

1. 参考的是哪个 App？最在意它的哪一点？
2. **必做**的核心功能（逐条列出，圈定 MVP）
3. 可以**砍掉 / 简化**的功能
4. 目标设备形态（手机 / 电视 / 平板 / 盒子）
5. 有没有界面参考（截图 / 描述 / 配色）
6. 数据从哪来？要不要**兼容原 App 的数据 / 文件格式**？
7. 要哪些权限、要不要联网
8. 用哪把签名证书（复用个人证书才能覆盖升级）

产出：功能清单（必做 / 可选 / 不做）+ 一句话定位 + 设备形态，再进入选型。
详见 `references/replicate-app.md`。

## 安装到 WorkBuddy

把整个目录解压到 `~/.workbuddy/skills/android-app-zero-to-one/`，刷新技能列表即可在对话中触发。

## 目录结构

```
SKILL.md                      六阶段工作流
scripts/setup_toolchain.py    自动部署 JDK + Android SDK
scripts/setup_keystore.py     生成个人签名证书
scripts/build_apk.py           七步构建器（自动处理 .bat、dex 注入、对齐、签名、验签）
references/                    构建链 / 踩坑 / 设备形态差异
assets/starter-project/       最小可编译骨架
```

## 许可

MIT —— 见 [LICENSE](LICENSE)。
