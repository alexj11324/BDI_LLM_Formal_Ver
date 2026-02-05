#!/bin/bash
# Ralph 监控脚本 - 实时查看进度

echo "════════════════════════════════════════════════════════════"
echo "🔄 Ralph Loop 实时监控"
echo "════════════════════════════════════════════════════════════"
echo ""

# 检查 Ralph 进程
if pgrep -f ralph_loop.sh > /dev/null; then
    echo "✅ Ralph 进程状态: 运行中"
    PROCESS_COUNT=$(pgrep -f ralph_loop.sh | wc -l | xargs)
    echo "   进程数量: $PROCESS_COUNT"
else
    echo "❌ Ralph 进程状态: 未运行"
    exit 1
fi

echo ""
echo "────────────────────────────────────────────────────────────"
echo "📊 当前状态 (.ralph/status.json)"
echo "────────────────────────────────────────────────────────────"
if [ -f .ralph/status.json ]; then
    cat .ralph/status.json | jq '.'
else
    echo "状态文件尚未创建"
fi

echo ""
echo "────────────────────────────────────────────────────────────"
echo "📝 最近的日志 (.ralph/logs/ralph.log)"
echo "────────────────────────────────────────────────────────────"
tail -15 .ralph/logs/ralph.log

echo ""
echo "────────────────────────────────────────────────────────────"
echo "📁 修改的文件 (git status)"
echo "────────────────────────────────────────────────────────────"
git status --short

echo ""
echo "════════════════════════════════════════════════════════════"
echo "💡 提示:"
echo "   - 查看完整日志: tail -f .ralph/logs/ralph.log"
echo "   - 停止 Ralph: pkill -f ralph_loop.sh"
echo "   - 重新运行监控: ./monitor_ralph.sh"
echo "════════════════════════════════════════════════════════════"
