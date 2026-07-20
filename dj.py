import json
import os
import time
import requests
from playwright.sync_api import sync_playwright

# ==================== 🧩 配置区（账号密码直接写入） ====================
DJI_USERNAME = "15247323191"          # 你的大疆账号
DJI_PASSWORD = "!!!TbR104"            # 你的大疆密码
PUSHPLUS_TOKEN = "db8ea6c096664161ad8351f3b9d8dd00"                    # 推送token，不需要则留空

OLD_DEVICE_MODEL = "精灵 Phantom 3 全系列"
OLD_SERIAL = "0JXUE5Q0A1816E"

TARGET_URL = "https://support.dji.com/recycle/apply"
STATE_FILE = "dji_cache.json"

HEADLESS = True   # 调试时保持 False，方便观察
# ====================================================================

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

def get_current_items():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',   # 去掉自动化标识
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        # 关键：去掉 navigator.webdriver 标志
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        
        page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"})

        page.goto(TARGET_URL, timeout=30000)
        page.wait_for_load_state("networkidle")
        page.screenshot(path="page_loaded.png")   # 保存截图
        
        # ---------- 1. 强制登录 ----------
        print("🔐 执行账号密码登录...")

        try:
            page.locator("text=微信扫码").wait_for(state="visible", timeout=15000)
            print("  ✅ 登录页面已加载")
        except:
            print("  ⚠️ 未检测到登录页面，可能已登录")

        # 点击“密码登录”
        clicked = False
        selectors = [
            'a[data-usagetag="password_login_tab"]',
            'text=密码登录',
            'div.ac-tab-item:has-text("密码登录")'
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    el.wait_for(state="visible", timeout=3000)
                    el.click(force=True)
                    print(f"  ✅ 点击密码登录成功（选择器: {sel}）")
                    clicked = True
                    break
            except:
                continue
        if not clicked:
            try:
                page.evaluate('document.querySelector(\'a[data-usagetag="password_login_tab"]\')?.click()')
                print("  ✅ 使用JS点击密码登录")
                clicked = True
            except:
                pass
        if not clicked:
            page.screenshot(path="error_cannot_click_tab.png")
            raise Exception("无法点击'密码登录'，截图已保存")

        page.wait_for_timeout(500)

        # 填写账号
        try:
            username_input = page.locator('input[name="username"]')
            username_input.wait_for(state="visible", timeout=30000)
            username_input.fill(DJI_USERNAME)
            print("  ✅ 填写账号")
        except Exception as e:
            print(f"  ❌ 填写账号失败: {e}")
            page.screenshot(path="error_username.png")
            raise

        # 填写密码
        try:
            password_input = page.locator('input[type="password"]')
            password_input.wait_for(state="visible", timeout=10000)
            password_input.fill(DJI_PASSWORD)
            print("  ✅ 填写密码")
        except Exception as e:
            print(f"  ❌ 填写密码失败: {e}")
            page.screenshot(path="error_password.png")
            raise

        # 点击登录
        try:
            login_btn = page.locator('button:has-text("登录")').first
            login_btn.wait_for(state="visible", timeout=5000)
            login_btn.click()
            print("  ✅ 点击登录按钮")
        except Exception as e:
            print(f"  ❌ 点击登录按钮失败: {e}")
            page.screenshot(path="error_login_btn.png")
            raise

        # 等待登录成功
        try:
            page.locator("text=微信扫码").first.wait_for(state="hidden", timeout=20000)
            print("✅ 登录成功（微信扫码消失）")
        except:
            try:
                page.wait_for_url(lambda url: "login" not in url, timeout=10000)
                print("✅ 登录成功（URL跳转）")
            except:
                page.screenshot(path="login_timeout.png")
                raise Exception("登录超时，可能遇到验证码")

        # ---------- 2. 登录成功后截图，查看跳转后的页面 ----------
        print("📍 当前 URL:", page.url)
        page.screenshot(path="after_login_before_apply.png")
        print("📸 已截图保存为 after_login_before_apply.png，请查看此页面是否有'立即申请'按钮")

        # ---------- 3. 检查并点击“立即申请” ----------
        # 等待页面稳定
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # 检查是否存在“立即申请”按钮（多种文本变体）
        apply_btn = page.locator("text=立即申请")
        if apply_btn.count() > 0:
            print("🔘 检测到'立即申请'按钮，正在点击...")
            try:
                apply_btn.first.click(timeout=5000)
                print("  ✅ 已点击'立即申请'")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"  ❌ 点击'立即申请'失败: {e}")
                page.screenshot(path="error_apply_btn.png")
                raise
        else:
            print("✅ 未检测到'立即申请'按钮，可能已在申请页面")

        # ---------- 4. 填写旧机信息 ----------
        # 再次确保在目标页面
        page.screenshot(path="old_tel.png")
        if "recycle/apply" not in page.url:
            print("⚠️ 不在回收申请页面，尝试重新跳转...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state("networkidle")

        has_old_info = page.locator("text=旧机信息").count() > 0
        has_serial_input = page.locator("input[placeholder*='序列号'], input[placeholder*='SN']").count() > 0

        if has_old_info or has_serial_input:
            print("📝 检测到旧机信息页面，开始自动填写...")

            # 点击下拉框选择旧机型
            combo_clicked = False
            try:
                combo = page.locator('[role="combobox"]').first
                combo.wait_for(state="visible", timeout=5000)
                combo.click()
                combo_clicked = True
                print("  ✅ 通过 role='combobox' 点击下拉框")
            except:
                pass
            if not combo_clicked:
                try:
                    combo = page.locator("text=请选择旧机型").first
                    combo.wait_for(state="visible", timeout=5000)
                    combo.click()
                    combo_clicked = True
                    print("  ✅ 通过文本 '请选择旧机型' 点击下拉框")
                except:
                    pass
            if not combo_clicked:
                try:
                    combo = page.locator(".ac-select, .atom-select, .ant-select").first
                    combo.wait_for(state="visible", timeout=5000)
                    combo.click()
                    combo_clicked = True
                    print("  ✅ 通过 class 选择器点击下拉框")
                except:
                    pass
            if not combo_clicked:
                page.screenshot(path="error_combo_click.png")
                raise Exception("无法点击旧机型下拉框")

            # 选择指定机型
            try:
                page.locator(f"text={OLD_DEVICE_MODEL}").first.click(timeout=5000)
                print(f"  ✅ 选择机型: {OLD_DEVICE_MODEL}")
            except Exception as e:
                print(f"  ❌ 选择机型失败: {e}")
                page.screenshot(path="error_select_model.png")
                raise

            # 填写序列号
            try:
                serial_input = page.locator("input[placeholder*='序列号'], input[placeholder*='SN']").first
                serial_input.wait_for(state="visible", timeout=10000)
                serial_input.fill(OLD_SERIAL)
                print(f"  ✅ 填写序列号: {OLD_SERIAL}")
            except Exception as e:
                print(f"  ❌ 填写序列号失败: {e}")
                page.screenshot(path="error_serial.png")
                raise

            # 点击下一步/查询
            try:
                btn = page.locator("button:has-text('下一步'), button:has-text('查询')").first
                btn.wait_for(state="visible", timeout=15000)
                btn.click()
                print("  ✅ 点击下一步/查询按钮")
            except Exception as e:
                print(f"  ❌ 点击下一步/查询失败: {e}")
                page.screenshot(path="error_next_btn.png")
                raise

            page.screenshot(path="change.png")
            # 等待进入换购方案页面
            try:
                page.wait_for_selector('.app-form, .atom-select', timeout=15000)
                print("✅ 已进入换购方案页面")
            except:
                page.screenshot(path="error_enter_plan.png")
                raise Exception("进入换购方案页面超时")
        else:
            print("✅ 未检测到旧机信息填写区域，假定已在换购方案页面")

        # ---------- 5. 抓取下拉框机型列表 ----------
        print("🔄 正在展开下拉框并抓取列表...")

        dropdown_selectors = ['.atom-select', '.ant-select', '.ac-select', '[role="combobox"]']
        dropdown = None
        for sel in dropdown_selectors:
            try:
                dropdown = page.locator(sel).first
                dropdown.wait_for(state="visible", timeout=3000)
                print(f"  ✅ 找到下拉框: {sel}")
                break
            except:
                continue
        if dropdown is None:
            page.screenshot(path="error_dropdown_not_found.png")
            raise Exception("未找到任何下拉框元素")

        expanded = False
        for attempt in range(3):
            try:
                dropdown.scroll_into_view_if_needed()
                dropdown.click()
                page.wait_for_selector('[role="option"]', state="visible", timeout=5000)
                expanded = True
                break
            except Exception as e:
                print(f"  🔄 下拉框展开尝试 {attempt+1} 失败: {e}")
                page.wait_for_timeout(1000)
        if not expanded:
            try:
                page.evaluate('document.querySelector(".atom-select, .ant-select, .ac-select, [role=\'combobox\']")?.click()')
                page.wait_for_selector('[role="option"]', state="visible", timeout=5000)
                expanded = True
                print("  ✅ 使用 JS 点击展开下拉框")
            except:
                page.screenshot(path="error_expand_dropdown.png")
                raise Exception("无法展开下拉框")

        option_elements = page.locator('[role="option"]')
        items = option_elements.all_inner_texts()
        items = [item.strip() for item in items if item.strip()]
        items = [i for i in items if 'DJI' in i or '套装' in i or '创作者' in i]
        items = sorted(set(items))

        if not items:
            print("⚠️ 未抓取到任何机型，尝试不过滤...")
            items = option_elements.all_inner_texts()
            items = [item.strip() for item in items if item.strip()]
            items = sorted(set(items))

        print(f"🎯 当前机型列表（共 {len(items)} 款）：")
        for idx, item in enumerate(items, 1):
            print(f"  {idx}. {item}")

        browser.close()
        return items

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
