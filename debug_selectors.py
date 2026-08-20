"""
Chạy script này khi tool báo lỗi selector.
Nó mở trình duyệt, vào ChatGPT rồi in ra các element tìm thấy.
Dùng kết quả để cập nhật TEXTAREA_SELECTORS trong chatgpt_agent.py
"""
import asyncio
import sys
sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])

from playwright.async_api import async_playwright
import config


async def debug_chatgpt():
    print("=== DEBUG ChatGPT Selectors ===")
    playwright = await async_playwright().start()
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(config.BROWSER_DATA_DIR / "chatgpt"),
        headless=False,
        viewport={"width": 1280, "height": 900},
    )
    page = context.pages[0] if context.pages else await context.new_page()

    print("Đang mở ChatGPT...")
    await page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
    await asyncio.sleep(4)

    print(f"URL: {page.url}")
    print(f"Title: {await page.title()}")
    print()

    # Tìm tất cả textarea và contenteditable
    candidates = await page.evaluate("""
    () => {
        const results = [];
        // textarea elements
        document.querySelectorAll('textarea').forEach(el => {
            results.push({
                tag: 'textarea',
                id: el.id,
                placeholder: el.placeholder,
                visible: el.offsetParent !== null,
                selector: el.id ? '#' + el.id : 'textarea'
            });
        });
        // contenteditable divs
        document.querySelectorAll('div[contenteditable="true"]').forEach(el => {
            results.push({
                tag: 'div[contenteditable]',
                id: el.id,
                ariaLabel: el.getAttribute('aria-label'),
                class: el.className.substring(0, 60),
                visible: el.offsetParent !== null,
                selector: el.id ? '#' + el.id : 'div[contenteditable="true"]'
            });
        });
        return results;
    }
    """)

    print("=== Các ô nhập liệu tìm thấy: ===")
    for i, el in enumerate(candidates):
        print(f"[{i+1}] {el}")

    print()
    # Tìm nút send
    btns = await page.evaluate("""
    () => {
        const results = [];
        document.querySelectorAll('button').forEach(btn => {
            const label = btn.getAttribute('aria-label') || btn.textContent.trim().substring(0, 30);
            const testid = btn.getAttribute('data-testid') || '';
            if (label || testid) {
                results.push({ label, testid, type: btn.type });
            }
        });
        return results.slice(0, 20);
    }
    """)
    print("=== Các nút (20 đầu tiên): ===")
    for b in btns:
        print(f"  {b}")

    input("\nNhấn Enter để đóng trình duyệt...")
    await context.close()
    await playwright.stop()


if __name__ == "__main__":
    asyncio.run(debug_chatgpt())
