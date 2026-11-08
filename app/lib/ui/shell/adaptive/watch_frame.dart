import 'package:flutter/material.dart';

import '../../../performance/device_class.dart';

/// 手表上的一层：把整页按 [DeviceClass.watchScale] 缩小后再画。
///
/// 为什么不是「把小屏的每一页重排一遍」：这个界面是按 320dp 起排的手机界面，
/// 手表只有 294dp 宽。逐页重排要动几百个布局，改不完也验不了；把窗口的逻辑尺寸
/// 放大 1/0.9、再用 [FittedBox] 缩回屏幕，等于告诉整棵树「你有 327dp」——
/// 所有断点、Row、网格都在它们本来就设计过的宽度里工作，横向溢出从根上消失。
///
/// 缩放是等比、绕中心，点击命中会跟着 [Transform] 一起缩，不用单独换算坐标。
/// 系统字体放大在手表中被夹到 1.0：1.3 倍的字体在 294dp 上必然溢出，这是手表
/// 上唯一说得通的取舍。
class WatchFrame extends StatelessWidget {
  const WatchFrame({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.maybeOf(context);
    if (!DeviceClass.isWatch || media == null || media.size.isEmpty) return child;
    final scale = DeviceClass.watchScale;
    final inflated = Size(media.size.width / scale, media.size.height / scale);
    // 边距按同样的比例放大，缩回去之后状态栏、导航条还是原来的物理高度。
    EdgeInsets scaled(EdgeInsets insets) => insets / scale;
    return FittedBox(
      fit: BoxFit.scaleDown,
      alignment: Alignment.center,
      child: SizedBox(
        width: inflated.width,
        height: inflated.height,
        child: MediaQuery(
          data: media.copyWith(
            size: inflated,
            padding: scaled(media.padding),
            viewPadding: scaled(media.viewPadding),
            viewInsets: scaled(media.viewInsets),
            systemGestureInsets: scaled(media.systemGestureInsets),
            textScaler: media.textScaler.clamp(maxScaleFactor: 1),
          ),
          child: child,
        ),
      ),
    );
  }
}
