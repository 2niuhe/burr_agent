#!/usr/bin/env python3
"""
启动脚本：运行 Vibe Workflow NiceGUI 应用
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# 确保当前目录在Python路径中
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# 设置环境变量（如果需要）
if not os.getenv("LLM_API_KEY"):
    print("⚠️  警告: 未设置 LLM_API_KEY 环境变量")
if not os.getenv("LLM_BASE_URL"):
    print("⚠️  警告: 未设置 LLM_BASE_URL 环境变量")
if not os.getenv("LLM_MODEL"):
    print("⚠️  警告: 未设置 LLM_MODEL 环境变量")
if not os.getenv("MCP_SERVER_URL"):
    print("⚠️  警告: 未设置 MCP_SERVER_URL 环境变量")

if __name__ == "__main__":
    print("🚀 启动 Vibe Workflow NiceGUI 应用...")
    print("📝 访问 http://localhost:8080 来使用应用")
    print("🔄 工作流管理页面: http://localhost:8080")
    print("💬 对话执行页面: http://localhost:8080/chat")
    print()
    
    try:
        # 导入并运行UI
        from ui import ui
        ui.run(
            title="Vibe Workflow UI",
            port=8080,
            show=True,
            reload=False
        )
    except KeyboardInterrupt:
        print("\n👋 再见!")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)
