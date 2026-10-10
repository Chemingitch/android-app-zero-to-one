# 设备形态差异（按需查阅）

**构建流程对所有形态完全一致**，差别只在 manifest 声明、交互方式和 minSdk。
做普通手机应用不需要看这个文件。

## 选型速查

| 形态 | minSdk 建议 | 关键差异 |
|---|---|---|
| 手机 | 21~24 | 触摸交互，最省心，默认按这个来 |
| 平板 | 21~24 | 布局要适配大屏 / 横屏，可用 `sw600dp` 资源限定符 |
| 电视 / 盒子 | 21（老设备）或 26 | 遥控器方向键交互，必须声明 touchscreen 非必需 |
| 穿戴 | 23+ | 另有一套 Wear OS 依赖，命令行链不适用 |

## 电视 / 盒子（最常见的特殊形态）

这几条**不做会导致装不上**，不是可选优化：

```xml
<!-- 不声明的话，Android TV 和多数厂商 ROM（含 TCL / 乐华）的安装器会直接过滤掉 -->
<uses-feature android:name="android.hardware.touchscreen" android:required="false" />
<uses-feature android:name="android.hardware.faketouch" android:required="false" />

<!-- 电视应用列表里才看得到 -->
<category android:name="android.intent.category.LEANBACK_LAUNCHER" />
```

其它要点：

- `<application android:banner="@mipmap/ic_launcher">`：电视主界面显示的横幅图
- **遥控器焦点**：普通手机应用靠触摸，电视靠方向键。可聚焦控件要加
  `android:focusable="true"`，并提供 selector 的 `state_focused` 描边高亮，
  否则遥控器移动时完全看不出选中了谁
- 焦点顺序：靠 `nextFocusDown/Up/Left/Right` 显式指定，避免焦点跳到奇怪的地方
- 桌面类应用还要 `category.HOME` + `category.DEFAULT`

## minSdk 决定的能力边界

| minSdk | 影响 |
|---|---|
| < 21 | vector drawable 不可用；`<adaptive-icon>`（mipmap-anydpi-v26）解析不到，必须提供 `mipmap-{mdpi,hdpi,xhdpi,xxhdpi}/ic_launcher.png` 兜底，否则图标空白 |
| < 23 | 无运行时权限模型，权限在安装时授予 |
| < 26 | 无自适应图标、无通知渠道 |
| < 29 | 无分区存储限制 |

## ABI

纯 Java、不含 `.so` 的 APK 是 **ABI 无关**的，不需要为 armeabi-v7a / arm64-v8a 分别出包。
只有引入 native 库时才需要按 ABI 拆分。
