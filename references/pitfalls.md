# 踩过的坑

按"会卡住多久"排序。前三条每一条都能让人卡半小时以上。

## 1. 批处理里调 d8 / apksigner 必须加 `call`

`d8.bat` 和 `apksigner.bat` 本身也是批处理。不加 `call` 时 cmd 会**直接跳过去且不再返回**，
脚本剩余步骤全部不执行，最终还返回成功退出码 —— 表现为"构建静默成功但产物是旧的或不存在"。

```bat
call "%BT%\d8.bat" --lib "%ANDROID_JAR%" --release --output dex obj\*.class
call "%BT%\apksigner.bat" sign --ks app.jks ... --out app.apk aligned.apk
```

用 `scripts/build_apk.py` 可完全绕开：它对 `.bat` 自动走 `cmd /c`。

## 2. .bat 文件必须纯 ASCII（或整体存成 GBK）

cmd.exe 按本地代码页（936/GBK）**逐字节**解析 bat。文件存成 UTF-8 时中文注释会被切碎整行，
报一堆 `'xxx' 不是内部或外部命令`，且错误行号毫无规律。

- 在 bat 里加 `chcp 65001` 救不了：带括号的语句块会被一次性读入，chcp 还没执行
- 正确做法：bat 只写 ASCII，或把文件整体编码成 GBK 落盘
- 同理，含空格的路径用 `setx` 会报"默认选项不允许超过 '2' 次"，
  改用 `[System.Environment]::SetEnvironmentVariable(..., 'User')`

## 3. apksigner 找不到 JAVA_HOME

从 Git Bash 直接调 `apksigner.bat` 报 `JAVA_HOME is not set and no 'java' command could be found`。
bat 不继承子进程 export 的变量，必须先 `export JAVA_HOME=<jdk>` 并加进 PATH。

## 4. PKCS12 里 key 密码必须等于 store 密码

`-storepass` 与 `-keypass` 设成两个不同的随机密码，签名时一定报：

```
java.security.UnrecoverableKeyException: Get Key failed:
Given final block not properly padded.
```

JDK 9 起 keytool 默认生成 PKCS12，它不支持独立于库密码的私钥密码。
**两处用同一个密码**（或显式加 `-storetype JKS`）。

## 5. 签名身份只有一份，丢了就不能升级

Android 靠"签名一致"判定这是同一个应用的新版本。换证书 → 用户必须先卸载旧版，数据全丢。

- 一把个人证书签你所有的应用（见 SKILL.md「个人签名证书」）
- `personal.jks` + `keystore.properties` **一起备份**，缺一不可
- 不要把它提交进仓库、不要塞进 skill 分发出去 —— 谁拿到谁能冒充你发布
- 只用临时 `debug.jks` 签的包**将来无法升级**，脚本会打 WARNING 提示

## 6. 步骤顺序

- `aapt2 link` 加 `--java <dir>` 才会生成 `R.java`；**必须 link 之后** javac 才能编译引用 `R.layout.*` 的源码
- `aapt2 link` 只产资源包，**不含代码**。`classes.dex` 要用 zipfile 手动塞进 apk 根目录
- `zipalign` 必须在 `apksigner` **之前**；签名后再对齐会破坏 v2 签名

## 7. minSdk 决定哪些资源能解析

- vector drawable 需要 API 21+
- `mipmap-anydpi-v26` 的自适应图标在 API 26 以下解析不到，必须同时提供各密度 PNG 兜底
- 更多边界见 `device-variants.md`

## 8. 列出其它已安装应用

Android 11+ 上 `queryIntentActivities` 会返回空，除非在 manifest 声明：

```xml
<uses-permission android:name="android.permission.QUERY_ALL_PACKAGES" />
<queries>
    <intent>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
    </intent>
</queries>
```

## 9. 验证不能只信退出码

- `apksigner verify` 成功时**几乎不输出**，失败才报错；要看证书得加 `--print-certs`
- 构建脚本报成功，但 dex 可能根本没进去 —— 用 `aapt2 dump badging` 确认入口 Activity，
  用 `unzip -l` 确认 `classes.dex` 在包里
- 签名会生成 `<apk>.idsig`，分发前删掉

## 10. 路径含空格

工具链路径常含空格（如 `C:\My Tools\android-sdk`）。Python 里拼接命令要传**列表**而非字符串，
避免 shell 拆词；bat 里则一律给路径加引号。
