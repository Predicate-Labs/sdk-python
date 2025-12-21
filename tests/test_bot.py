from sentience.browser import SentienceBrowser

def test_bot():
    browser = SentienceBrowser()
    browser.start()
    browser.page.goto("https://bot.sannysoft.com")
    browser.page.wait_for_timeout(1000)
    browser.page.screenshot(path="screenshot.png")
    browser.close()


if __name__ == "__main__":
    test_bot()