import json
import time
import os
import requests
from playwright.sync_api import sync_playwright


# ==================== 🧩 配置区（请修改） ====================
TARGET_URL = "https://support.dji.com/recycle/apply"
STATE_FILE = "dji_cache.json"
STORAGE_STATE_FILE = "dji_storage_state.json"   # ← 新增，用于保存登录状态

# 🛠️ 你的旧机信息（请务必填写正确）
OLD_DEVICE_MODEL = "精灵 Phantom 3 全系列"  # 旧机型的完整名称（必须与下拉选项一字不差）
OLD_SERIAL = "0JXUE5Q0A1816E"  # 你的设备序列号

# 📱 微信推送（PushPlus）
# 去 http://www.pushplus.plus 注册 -> 一对一推送 -> 复制你的 Token
PUSHPLUS_TOKEN = "db8ea6c096664161ad8351f3b9d8dd00"  # 填好后，脚本运行完会自动推送到你微信


# =============================================================

def get_current_items():
    with sync_playwright() as p:
        browser = p.chromium.launch(
        headless=True,args=[
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu'
        ]
        )

        # ===== 【修改】创建带状态的 context =====
        if os.path.exists(STORAGE_STATE_FILE):
            context = browser.new_context(storage_state=STORAGE_STATE_FILE)
        else:
            context = browser.new_context()
        page = context.new_page()                     # 用 context 创建 page

        page.set_extra_http_headers({"User-Agent": "Mozilla/5.0"})
        page.goto(TARGET_URL, timeout=30000)
        page.wait_for_load_state("networkidle")

        # ===== 【新增】登录检测与扫码等待 =====
        # 检测是否有“微信扫码”文本（登录弹窗）
        login_indicator = page.locator("text=微信扫码")
        if login_indicator.count() > 0:
            print("⚠️ 检测到登录要求，请扫描二维码登录（超时5分钟）...")
            # 等待该文本消失（即登录成功）
            login_indicator.first.wait_for(state='hidden', timeout=300000)
            print("✅ 登录成功，保存状态...")
            context.storage_state(path=STORAGE_STATE_FILE)
        else:
            print("✅ 已登录（或无需登录），更新状态...")
            # 每次运行都保存一次，保持 cookie 最新
            context.storage_state(path=STORAGE_STATE_FILE)
        # ---------- 1. 旧机信息填写（原样） ----------
        if page.locator("text=旧机信息").count() > 0 or page.locator("input[placeholder*='序列号']").count() > 0:
            print("📝 检测到旧机信息页面，开始自动填写...")
            try:
                page.locator('[role="combobox"]').first.click(timeout=3000)
            except:
                page.locator("text=请选择旧机型").click(timeout=3000)
            page.locator(f"text={OLD_DEVICE_MODEL}").click(timeout=3000)
            serial_input = page.locator("input[placeholder*='序列号'], input[placeholder*='SN']").first
            serial_input.fill(OLD_SERIAL)
            try:
                page.locator("button:has-text('下一步')").click(timeout=3000)
            except:
                page.locator("button:has-text('查询')").click(timeout=3000)
            page.wait_for_selector('.app-form', timeout=15000)
            print("✅ 已进入换购方案页面")
        else:
            print("✅ 已在换购方案页面")

        # ---------- 2. 抓取换购机型下拉列表（新方案） ----------
        # 等待下拉框容器稳定并可见
        dropdown = page.locator('.atom-select').first
        dropdown.wait_for(state='visible', timeout=15000)

        # 尝试点击展开下拉，如果点击后元素失效则重试
        for attempt in range(3):
            try:
                # 重新获取元素以确保最新
                dropdown = page.locator('.atom-select').first
                dropdown.scroll_into_view_if_needed()
                dropdown.click()  # 直接点击，而不是坐标点击
                # 等待选项出现
                page.wait_for_selector('[role="option"]', state='visible', timeout=10000)
                break
            except Exception as e:
                print(f"🔄 下拉框操作尝试 {attempt + 1} 失败，重试中...")
                page.wait_for_timeout(1000)
                continue
        else:
            raise Exception("无法展开下拉框，请检查页面结构")


        # 提取所有选项文本
        option_elements = page.locator('[role="option"]')
        items = option_elements.all_inner_texts()
        items = [item.strip() for item in items if item.strip()]
        items = [i for i in items if 'DJI' in i or '套装' in i or '创作者' in i]
        items = sorted(set(items))

        print(f"🎯 当前机型列表（共 {len(items)} 款）：")
        for idx, item in enumerate(items, 1):
            print(f"  {idx}. {item}")

        browser.close()
        return items


# ---------- 缓存和推送逻辑 ----------
def load_old_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_new_state(items):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def send_pushplus(title, content):
    if not PUSHPLUS_TOKEN:
        return
    try:
        resp = requests.post("http://www.pushplus.plus/send", json={
            "token": PUSHPLUS_TOKEN,
            "title": title,
            "content": content
        })
        if resp.status_code == 200:
            print("✅ 微信推送成功")
        else:
            print(f"⚠️ 推送失败: {resp.text}")
    except Exception as e:
        print(f"⚠️ 推送异常: {e}")


def main():
    print("🚀 启动大疆焕新监控...")
    old_list = load_old_state()
    new_list = get_current_items()

    if not new_list:
        print("⚠️ 未获取到任何数据，请检查网络或页面是否变动")
        return

    if old_list != new_list:
        added = set(new_list) - set(old_list)
        removed = set(old_list) - set(new_list)
        msg = f"🔄 机型列表已更新！\n当前共 {len(new_list)} 款机型\n\n"
        if added:
            msg += f"➕ 新增：{', '.join(added)}\n"
        if removed:
            msg += f"➖ 下架：{', '.join(removed)}\n"
        msg += f"\n👉 查看详情：{TARGET_URL}"

        print("📨 检测到变化，发送微信通知...")
        send_pushplus("大疆焕新机型变更提醒", msg)
        save_new_state(new_list)
    else:
        print("✅ 列表无变化，无需推送")


if __name__ == "__main__":
    main()

'''
def main():
    print("🚀 启动大疆焕新监控...")
    old_list = load_old_state()
    new_list = get_current_items()

    if not new_list:
        print("⚠️ 未获取到任何数据，请检查网络或页面是否变动")
        return

    if old_list != new_list:
        added = set(new_list) - set(old_list)
        removed = set(old_list) - set(new_list)
        msg = f"🔄 机型列表已更新！\n当前共 {len(new_list)} 款机型\n\n"
        if added:
            msg += f"➕ 新增：{', '.join(added)}\n"
        if removed:
            msg += f"➖ 下架：{', '.join(removed)}\n"
        msg += f"\n👉 查看详情：{TARGET_URL}"

        print("📨 检测到变化，发送微信通知...")
        send_pushplus("大疆焕新机型变更提醒", msg)
        save_new_state(new_list)
    else:
        # ===== 新增：无变化时也发送测试推送 =====
        print("📨 列表无变化，发送测试推送...")
        test_msg = f"✅ 监控运行正常\n当前共 {len(new_list)} 款机型\n列表无变化（测试推送）\n\n👉 查看详情：{TARGET_URL}"
        send_pushplus("大疆焕新监控测试", test_msg)
        # =======================================

if __name__ == "__main__":
    main()
'''
