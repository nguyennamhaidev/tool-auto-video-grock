"""Inspect Grok post page - gửi 1 request thật để lấy cấu trúc."""
import asyncio

async def inspect():
    try:
        from rebrowser_playwright.async_api import async_playwright
    except ImportError:
        from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]

        # Tìm tab imagine nếu có
        page = None
        for p in ctx.pages:
            if "grok.com" in p.url:
                page = p
                print(f"Dung tab san: {p.url}")
                break
        if not page:
            page = await ctx.new_page()
            await page.goto("https://grok.com/imagine", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)

        print(f"URL: {page.url}")

        # Gửi 1 prompt nhanh để có post page
        textarea = await page.query_selector(".tiptap.ProseMirror")
        if textarea:
            # Chon Video
            radios = await page.query_selector_all("button[role='radio']")
            for r in radios:
                if (await r.text_content() or "").strip() == "Video":
                    await r.click()
                    await asyncio.sleep(0.5)
                    break

            await textarea.click()
            await asyncio.sleep(0.3)
            await page.evaluate("""(t) => {
                const el = document.querySelector('.tiptap.ProseMirror');
                if (el) { el.focus(); document.execCommand('insertText', false, t); }
            }""", "A Vietnamese woman walking in the park, cinematic 4K, 10 seconds")
            await asyncio.sleep(0.5)

            submit = await page.query_selector("button[aria-label='Submit'][type='submit']")
            if submit:
                await submit.click()
                print("Submitted! Waiting for post page...")

                # Chờ navigate sang post page
                for _ in range(30):
                    await asyncio.sleep(1)
                    if "/imagine/post/" in page.url:
                        print(f"Post page: {page.url}")
                        break

                await asyncio.sleep(5)

        # Inspect elements
        print(f"\nFinal URL: {page.url}")

        # Video elements
        vids = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('video')).map(v => ({
                src: v.src || '',
                currentSrc: v.currentSrc || '',
                readyState: v.readyState,
                duration: v.duration || 0,
                w: v.getBoundingClientRect().width,
                h: v.getBoundingClientRect().height
            }));
        }""")
        print(f"\nVideos: {len(vids)}")
        for v in vids:
            print(f"  src={v['src'][:80]} ready={v['readyState']} dur={v['duration']:.1f} {v['w']:.0f}x{v['h']:.0f}")

        # Loading/progress elements
        prog = await page.evaluate("""() => {
            // Tim text co % (progress)
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            const texts = [];
            let n;
            while (n = walker.nextNode()) {
                const t = n.textContent.trim();
                if (t && (t.includes('%') || t.toLowerCase().includes('generat'))) {
                    texts.push(t.substring(0, 50));
                }
            }
            // Tim spinner/loading elements
            const spinners = Array.from(document.querySelectorAll('[class*="spin"], [class*="load"], [class*="progress"]'))
                .slice(0,5).map(e => e.className.substring(0,60));
            return { texts: [...new Set(texts)].slice(0,10), spinners };
        }""")
        print(f"\nProgress texts: {prog['texts']}")
        print(f"Spinners: {prog['spinners']}")

        # Buttons
        btns = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button, a[download]')).map(b => ({
                text: b.textContent.trim().substring(0,25),
                aria: b.getAttribute('aria-label') || '',
                type: b.type || ''
            })).filter(b => b.text || b.aria);
        }""")
        print(f"\nButtons:")
        for b in btns:
            print(f"  [{b['text']:<22}] aria={b['aria']}")

        await page.close()
        await browser.close()

asyncio.run(inspect())
