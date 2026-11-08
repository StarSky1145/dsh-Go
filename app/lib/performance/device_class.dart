import 'dart:io';

import 'package:flutter/widgets.dart';

/// 这台设备是不是手表（或同级别的小方屏）。
///
/// 判定只看屏幕：Android 上逻辑最短边不超过 [watchShortestSide] 就算手表。
/// 常见的手机最短边是 360dp，320dp 的老机器也还算手机，所以线画在 300：
/// 手表（比如 368×448 像素、200dpi，逻辑 294×358）在里面，手机在外面。
///
/// 读的是窗口本身，不是某次布局的约束，所以首帧之前就能回答：配色、性能档、
/// 启动路径都要在跑第一帧之前知道答案。
abstract final class DeviceClass {
  /// 逻辑最短边不超过它：手表。
  static const watchShortestSide = 300.0;

  /// 手表上把整页按这个比例缩小后再画（见 `ui/shell/adaptive/watch_frame.dart`）。
  ///
  /// 界面是按 320dp 起步的手机排的，294dp 直接铺会挤：缩小 10% 换回一寸宽度，
  /// 同时把「一行放不下」的横向溢出挡在出现之前。0.9 是折中：再小字就看不清了。
  static const watchScale = 0.9;

  static bool? _watch;

  /// 手表：极轻档界面（不动效、不模糊、不养宠物）与缩小排版的开关。
  static bool get isWatch => _watch ??= _detect();

  @visibleForTesting
  static void overrideForTesting(bool? watch) => _watch = watch;

  static bool _detect() {
    if (!Platform.isAndroid) return false;
    final view = WidgetsBinding.instance.platformDispatcher.implicitView;
    if (view == null) return false;
    final size = view.physicalSize / view.devicePixelRatio;
    if (size.isEmpty) return false;
    return size.shortestSide <= watchShortestSide;
  }
}
