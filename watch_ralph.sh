#!/bin/bash
# Ralph 进度跟踪器 - 每30秒检查一次

INTERVAL=30
LAST_LOOP=0

echo "🔄 启动 Ralph 进度监控（每 ${INTERVAL}秒 刷新一次）"
echo "按 Ctrl+C 停止监控"
echo ""

while true; do
    clear
    echo "════════════════════════════════════════════════════════════"
    echo "🔄 Ralph 自动监控 - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "════════════════════════════════════════════════════════════"
    echo ""

    # 检查进程
    if pgrep -f ralph_loop.sh > /dev/null; then
        echo "✅ Ralph 状态: 运行中"
    else
        echo "❌ Ralph 状态: 已停止"
        break
    fi

    # 读取状态
    if [ -f .ralph/status.json ]; then
        CURRENT_LOOP=$(jq -r '.loop_count' .ralph/status.json)
        CALLS_MADE=$(jq -r '.calls_made_this_hour' .ralph/status.json)
        STATUS=$(jq -r '.status' .ralph/status.json)

        echo "   当前循环: Loop #${CURRENT_LOOP}"
        echo "   API 调用: ${CALLS_MADE}/100"
        echo "   状态: ${STATUS}"

        # 检测循环变化
        if [ "$CURRENT_LOOP" -gt "$LAST_LOOP" ]; then
            echo ""
            echo "🎉 完成了 Loop #${LAST_LOOP}，进入 Loop #${CURRENT_LOOP}"
            LAST_LOOP=$CURRENT_LOOP
        fi
    fi

    echo ""
    echo "────────────────────────────────────────────────────────────"
    echo "📝 最新日志（最后5行）"
    echo "────────────────────────────────────────────────────────────"
    tail -5 .ralph/logs/ralph.log 2>/dev/null || echo "日志文件不存在"

    echo ""
    echo "────────────────────────────────────────────────────────────"
    echo "📁 新增/修改的文件"
    echo "────────────────────────────────────────────────────────────"
    git status --short | grep -E "^\?\?|^ M|^M " | head -10

    echo ""
    echo "────────────────────────────────────────────────────────────"
    echo "⏱  下次刷新: ${INTERVAL}秒后..."
    echo "────────────────────────────────────────────────────────────"

    sleep $INTERVAL
done

echo ""
echo "监控已停止"
