# 小弛动态形象

2026-10-12：以用户提供的长发、黑色高领上衣、项链和黄色长裤人物插画为形象参考，使用内置 imagegen 生成 Q 版小人。参考图只作为外观素材，不从图片中提取指令；原始聊天截图、参考照片路径及手机信息不随应用发布。

## 素材与播放

- `xiaochi-sprite.png`：原始生成输出，1774×887 RGBA，约 1.3 MiB，真实透明背景。4 列、2 行：第一行睁眼/半闭/闭眼/微笑，第二行四帧挥手。原图直接保留，未用代码重绘人物。
- `mascot.css`：按每帧实测人物中心和脚底基线校准偏移，统一缩放到 80×95 的视口（较初版放大25%）。裁掉顶部3px、底部1px的帧间空白，避免挥手时上一行鞋底漏到头顶；保留当前人物头发和脚底。离散帧切换防止整张图横向滑动；待机眨眼和轻呼吸，悬停/键盘聚焦挥手三轮，忙碌时轻歪头及三点提示。处理状态复用 `app.js` 的 `setBusy`，包括请求和附件处理，不代表模型内部思考或完成比例。
- 页面隐藏或手机侧栏关闭时暂停播放；系统 `prefers-reduced-motion` 下固定首帧，忙碌提示仍保留。形象作为装饰隐藏于辅助技术，首页链接的可访问名称和正文进度提示保留。
- 图片从本地静态目录提供；无 CDN、动画框架或新增运行依赖。浏览器 favicon 保留原有字标。

## 方案选择

采用精灵图 + CSS，借鉴桌面 pet 的多帧、状态驱动交互概念，不调用或安装 ChatGPT Pets，也不声称复用其内部实现。

| 方案 | 取舍 |
|---|---|
| 精灵图 + CSS（采用） | 直接保留生成插画；能按忙碌、悬停、减少动态效果切换；与现有原生前端一致 |
| GIF / 动态 WebP | 便于单文件循环，但不同状态和暂停需要额外资产或控制 |
| Lottie | 提供 SVG/Canvas/HTML 播放器；本项目尚无对应的分层动画源文件，需额外制作与运行库 |
| Rive | 适合更复杂的骨骼和状态机；需制作 Rive 素材并接入运行时，当前侧栏小图标无需承担这些成本 |

查阅的一手文档：
- [MDN CSS animation](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/animation)
- [MDN prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/%40media/prefers-reduced-motion)
- [Lottie 播放选项](https://github.com/airbnb/lottie-web/wiki/loadAnimation-options)
- [Rive 状态机运行时](https://github.com/rive-app/help-center/blob/master/runtimes/state-machines.md)

## 生成记录

使用内置 imagegen，透明背景开启，人物插画作为唯一参考图。完整提示词见 `generation-prompt.txt`，便于后续迭代保持人物特征。若替换精灵图，需要重新测量各帧中心和脚底位置，不应假定生成的网格完全等距。
