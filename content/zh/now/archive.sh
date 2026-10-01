#!/bin/bash
# content/zh/now/archive.sh
# 归档 _index.md 的正文，文件名和标题都用「年+月」格式

set -e
cd "$(dirname "$0")"

# ---------- 中文/阿拉伯数字转换 ----------

# 中文数字年份 → 阿拉伯数字（二〇二六 → 2026）
cn_year_to_num() {
    printf '%s' "$1" | sed 's/〇/0/g; s/一/1/g; s/二/2/g; s/三/3/g; s/四/4/g; s/五/5/g; s/六/6/g; s/七/7/g; s/八/8/g; s/九/9/g'
}

# 中文数字月份 → 阿拉伯数字（九 → 9，十 → 10，十一 → 11，十二 → 12）
cn_month_to_num() {
    case "$1" in
        一) echo 1 ;;
        二) echo 2 ;;
        三) echo 3 ;;
        四) echo 4 ;;
        五) echo 5 ;;
        六) echo 6 ;;
        七) echo 7 ;;
        八) echo 8 ;;
        九) echo 9 ;;
        十) echo 10 ;;
        十一) echo 11 ;;
        十二) echo 12 ;;
        *) echo "" ;;
    esac
}

# 阿拉伯数字年份 → 中文数字（2026 → 二〇二六）
num_year_to_cn() {
    printf '%s' "$1" | sed 's/0/〇/g; s/1/一/g; s/2/二/g; s/3/三/g; s/4/四/g; s/5/五/g; s/6/六/g; s/7/七/g; s/8/八/g; s/9/九/g'
}

# 阿拉伯数字月份 → 中文数字（9 → 九，10 → 十，11 → 十一，12 → 十二）
num_month_to_cn() {
    case "$1" in
        1) echo 一 ;;
        2) echo 二 ;;
        3) echo 三 ;;
        4) echo 四 ;;
        5) echo 五 ;;
        6) echo 六 ;;
        7) echo 七 ;;
        8) echo 八 ;;
        9) echo 九 ;;
        10) echo 十 ;;
        11) echo 十一 ;;
        12) echo 十二 ;;
        *) echo "" ;;
    esac
}

INDEX="_index.md"

if [ ! -f "$INDEX" ]; then
    echo "错误：找不到 $INDEX"
    exit 1
fi

# ---------- 检测 front matter 分隔符 ----------
FIRST_LINE=$(head -1 "$INDEX" | tr -d '\r')
if [ "$FIRST_LINE" = "+++" ]; then
    DELIM="+++"
    FM_FORMAT="toml"
elif [ "$FIRST_LINE" = "---" ]; then
    DELIM="---"
    FM_FORMAT="yaml"
else
    echo "错误：无法识别 front matter 分隔符，文件首行是：$FIRST_LINE"
    exit 1
fi

echo "检测到 front matter 格式：$FM_FORMAT（分隔符 $DELIM）"

# ---------- 提取正文 ----------
# 找到 front matter 结束行（第二个分隔符的行号）
END_LINE=$(awk -v d="$DELIM" '$0 == d { c++; if (c == 2) { print NR; exit } }' "$INDEX")

if [ -z "$END_LINE" ]; then
    echo "错误：无法定位 front matter 的结束行。"
    exit 1
fi

echo "front matter 结束于第 $END_LINE 行"

# 从下一行开始，全部作为正文
BODY=$(tail -n +$((END_LINE + 1)) "$INDEX")

if [ -z "$(echo "$BODY" | tr -d '[:space:]')" ]; then
    echo "错误：$INDEX 没有正文可以归档。"
    echo "提示：请确认正文写在第二个 $DELIM 之后。"
    exit 1
fi

# ---------- 从正文提取年月 ----------
# 去掉空格和 Tab，便于正则匹配
COMPACT=$(printf '%s' "$BODY" | tr -d ' \t')

# 匹配中文月份（支持九月、十二月等，允许带不带年份）
FIRST_MONTH=$(printf '%s\n' "$COMPACT" | grep -oE '(年)?[一二三四五六七八九十]+月' | head -n1)

if [ -n "$FIRST_MONTH" ]; then
    CN_MONTH=$(printf '%s' "$FIRST_MONTH" | sed -E 's/^(年)?([一二三四五六七八九十]+)月.*/\2/')
    MONTH=$(cn_month_to_num "$CN_MONTH")

    # 推断年份：如果当前是1月，而正文写的是12月，说明是去年归档的
    CURRENT_YEAR=$(date +%Y)
    CURRENT_MONTH=$(date +%-m)
    if [ "$MONTH" -gt "$CURRENT_MONTH" ]; then
        YEAR=$((CURRENT_YEAR - 1))
    else
        YEAR=$CURRENT_YEAR
    fi
    echo "已从正文提取月份：$CN_MONTH 月（推断年份：$YEAR 年）"
else
    # 完全兜底
    YEAR=$(date +%Y)
    MONTH=$(date +%-m)
    echo "警告：正文中未找到月份，使用当前年月：$YEAR 年 $MONTH 月"
fi

# 月份补零，用于文件名（2026-09 比 2026-9 排序更友好）
MONTH_PADDED=$(printf '%02d' "$MONTH")

# 文件名和标题
BASE_NAME="${YEAR}-${MONTH_PADDED}"
TARGET="${BASE_NAME}.md"
CN_YEAR=$(num_year_to_cn "$YEAR")
CN_MONTH=$(num_month_to_cn "$MONTH")
TITLE="${CN_YEAR}年  ${CN_MONTH}月"

echo "归档文件：$TARGET"
echo "归档标题：$TITLE"

# ---------- 同名文件检查 ----------
if [ -f "$TARGET" ]; then
    echo "警告：$TARGET 已存在。"
    read -r -p "是否覆盖？(y/N) " CONFIRM
    if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
        echo "已取消。"
        exit 0
    fi
fi

# ---------- 写入归档文件 ----------
if [ "$FM_FORMAT" = "toml" ]; then
    {
        echo "+++"
        echo "title = \"$TITLE\""
        echo "date = ${YEAR}-${MONTH_PADDED}-01"
        echo "+++"
        echo ""
        echo "$BODY"
    } > "$TARGET"
else
    {
        echo "---"
        echo "title: \"$TITLE\""
        echo "date: ${YEAR}-${MONTH_PADDED}-01"
        echo "---"
        echo ""
        echo "$BODY"
    } > "$TARGET"
fi

echo "✓ 已归档到：$TARGET"

# ---------- 清空 _index.md 正文 ----------
echo ""
read -r -p "清空 _index.md 正文并开始新的当下？(y/N) " CONFIRM

if [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ]; then
    head -n "$END_LINE" "$INDEX" > "$INDEX.tmp"
    echo "" >> "$INDEX.tmp"
    mv "$INDEX.tmp" "$INDEX"
    echo "✓ 已清空 _index.md 正文。"
fi

echo ""
echo "完成。"
