# tools/make_test_invoice.py
# -*- coding: utf-8 -*-

import os

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    out_dir = os.path.join(os.getcwd(), "test_assets")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "test_invoice.png")

    img = Image.new("RGB", (1200, 800), "white")
    draw = ImageDraw.Draw(img)

    # 尝试加载黑体；没有就用默认字体（不影响流程跑通）
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", 36)
        font_small = ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.rectangle([40, 40, 1160, 140], outline="black", width=3)
    draw.text((60, 70), "增值税普通发票（测试样例）", fill="black", font=font)

    draw.rectangle([40, 170, 1160, 520], outline="black", width=2)
    lines = [
        "发票代码：4400 1234 5678",
        "发票号码：98765432",
        "开票日期：2026-04-20",
        "购方名称：广州某某科技有限公司",
        "销方名称：广州某某酒店有限公司",
        "项目：住宿费",
        "金额（小写）：￥888.00",
        "价税合计（小写）：￥888.00",
    ]
    y = 190
    for t in lines:
        draw.text((60, y), t, fill="black", font=font_small)
        y += 40

    draw.rectangle([40, 550, 1160, 740], outline="black", width=2)
    draw.text((60, 580), "备注：此图片仅用于 OCR 测试，不含真实票据与个人信息。", fill="black", font=font_small)

    img.save(out_path)
    print("生成完成：", out_path)


if __name__ == "__main__":
    main()

# 自查点：
# 1) 运行成功后会生成：test_assets/test_invoice.png
# 2) 打开图片能看到：开票日期 2026-04-20、价税合计 ￥888.00
