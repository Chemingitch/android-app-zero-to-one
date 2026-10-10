# 构建链：工具清单与流程

设备形态无关 —— 手机、平板、电视、盒子走完全相同的七步。

## 目录布局

由 `scripts/setup_toolchain.py` 生成，默认装在 `~/.android-zero-to-one`
（`--dir` 可改）。分发给别人时**不要打包这个目录**，让它自己跑脚本生成。

```
<root>\
├── toolchain.json                         build_apk.py 自动读取的 jdk/sdk 位置
├── jdk-17\                                Temurin 17（压缩包内还套一层 jdk-17.0.x\）
│   └── jdk-17.0.x\bin\javac.exe, keytool.exe
├── android-sdk\
│   ├── cmdline-tools\latest\bin\sdkmanager.bat
│   ├── build-tools\
│   │   └── 34.0.0\                        默认使用（有多个版本时取最高）
│   │       ├── aapt2.exe                  资源编译 + 链接 + 生成 R.java
│   │       ├── d8.bat                     .class -> .dex
│   │       ├── apksigner.bat              v1/v2 签名 + 校验
│   │       └── zipalign.exe               4 字节对齐
│   ├── platforms\android-34\android.jar   javac / d8 的 API 依赖
│   └── platform-tools\adb.exe             安装到设备
└── certs\                                 你的签名身份，绝不外传
    ├── personal.jks                       个人证书（一把签所有应用）
    └── keystore.properties                alias + 密码，仅本人可读
```

`toolchain.json` 形如：

```json
{ "jdk": "<root>/jdk-17/jdk-17.0.20.1+1", "sdk": "<root>/android-sdk" }
```

## 各工具在流水线中的角色

| 步骤 | 工具 | 输入 → 输出 |
|---|---|---|
| 1 | `aapt2 compile` | `res/` → `compiled.zip`（二进制资源） |
| 2 | `aapt2 link` | compiled.zip + manifest → `unsigned.apk` + `R.java` |
| 3 | `javac` | `java/**/*.java` + `R.java` → `.class` |
| 4 | `d8` | `.class` → `classes.dex` |
| 5 | `zipfile`（Python） | 把 `classes.dex` 写进 apk 根目录 |
| 6 | `zipalign` | apk → 对齐后的 apk |
| 7 | `apksigner` | 对齐 apk → 已签名 apk（v1 + v2），随后自动 `verify` |

## 环境要求

- Python 3.8+（标准库即可，无第三方依赖）
- 网络：首次部署要下载 JDK（约 180 MB）+ command-line tools（约 140 MB）
- 不需要 Android Studio、不需要 Gradle、不需要管理员权限

## 常见命令

```bash
# 一次性部署工具链
python scripts/setup_toolchain.py                     # 装到 ~/.android-zero-to-one
python scripts/setup_toolchain.py --mirror cn         # 国内走清华镜像
python scripts/setup_toolchain.py --proxy http://127.0.0.1:7890

# 一次性创建个人签名身份
python scripts/setup_keystore.py --name "Your Name"

# 构建（自动读 toolchain.json + 个人证书，无需任何参数）
python scripts/build_apk.py --src <project> --min-sdk 21 --out app.apk

# 只编译不签名
python scripts/build_apk.py --src <project> --no-sign

# 校验签名（成功时几乎不输出）
apksigner.bat verify --print-certs app.apk

# 查看包信息
aapt2.exe dump badging app.apk

# 装到设备（电视上常需 -t -d 允许测试包与降级）
adb install -r -t -d app.apk
```

独立手工调用 `apksigner` / `aapt2` 时记得先 `export JAVA_HOME=<jdk>`。
