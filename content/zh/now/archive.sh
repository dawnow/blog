#!/bin/bash
# content/zh/now/archive.sh
# 归档 _index.md 的正文，文件名和标题都用「年+月」格式

set -e
cd "$(dirname "$0")"

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
BODY=$(awk -v d="$DELIM" '
  $0 == d { c++; next }
  c >= 2 { print }
' "$INDEX")

if [ -z "$(echo "$BODY" | tr -d '[:space:]')" ]; then
    echo "错误：$INDEX 没有正文可以归档。"
    echo "提示：请确认正文写在第二个 $DELIM 之后。"
    exit 1
fi

# ---------- 从正文提取年月 ----------
# 去掉空格和 Tab，方便正则匹配
COMPACT=$(printf '%s' "$BODY" | tr -d ' \t')
FIRST_DATE=$(printf '%s\n' "$COMPACT" | grep -oE '20[0-9]{2}年[0-9]{1,2}月' | head -n1)

if [ -n "$FIRST_DATE" ]; then
    YEAR=$(printf '%s' "$FIRST_DATE" | grep -oE '20[0-9]{2}')
    MONTH=$(printf '%s' "$FIRST_DATE" | sed -E 's/.*年([0-9]+)月.*/\1/')
    echo "已从正文提取：$YEAR 年 $MONTH 月"
else
    YEAR=$(date +%Y)
    MONTH=$(date +%-m 2>/dev/null || date +%m | sed 's/^0//')
    echo "警告：正文中未找到「YYYY 年 M 月」格式的日期，使用当前年月：$YEAR 年 $MONTH 月"
fi

# 月份补零，用于文件名（2026-09 比 2026-9 排序更友好）
MONTH_PADDED=$(printf '%02d' "$MONTH")

# 文件名和标题
BASE_NAME="${YEAR}-${MONTH_PADDED}"
TARGET="${BASE_NAME}.md"
TITLE="當下 · ${YEAR} 年 ${MONTH} 月"

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
    awk -v d="$DELIM" '
      BEGIN { c = 0 }
      $0 == d { c++; print; next }
      c <= 1 { print }
    ' "$INDEX" > "$INDEX.tmp"
    echo "" >> "$INDEX.tmp"
    mv "$INDEX.tmp" "$INDEX"
    echo "✓ 已清空 _index.md 正文。"
fi

echo ""
echo "完成。"
