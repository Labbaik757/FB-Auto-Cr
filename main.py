import os
import sys
import platform
from itertools import count

if platform.system() == "Windows":
    os.system('')
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from ui.logo import logo
from ui.colors import GREEN, RED, WHITE, YELLOW, CYAN, EKL, LINE
from ui.display import print_lock
from core.device_manager import select_device, select_browser, select_server
from core.proxy_manager import get_proxy_list, create_proxy_cycle, get_no_proxy_data
from core.password_manager import select_password_config
from core.number_manager import process_file_input
from core.path_manager import is_termux_or_mobile, get_base_storage_dir, get_output_dir
from core.counter import Counter


# Display current configuration state on screen
def render_config(config_state):
    logo()
    if is_termux_or_mobile():
        print(f" {GREEN}[{RED}●{GREEN}] Mode          {EKL} Mobile / Termux Storage")
        print(f" {GREEN}[{RED}●{GREEN}] Storage Folder{EKL} {get_base_storage_dir()}")
        print(f"{LINE}")
    print(f" {GREEN}[{RED}●{GREEN}] Device Type  {EKL} {config_state.get('device', '...')}")
    print(f" {GREEN}[{RED}●{GREEN}] Browser      {EKL} {config_state.get('browser', '...')}")
    print(f" {GREEN}[{RED}●{GREEN}] Server       {EKL} {config_state.get('server', '...')}")
    print(f" {GREEN}[{RED}●{GREEN}] Password     {EKL} {config_state.get('password', '...')}")
    print(f" {GREEN}[{RED}●{GREEN}] Proxy        {EKL} {config_state.get('proxy', '...')}")
    print(f" {GREEN}[{RED}●{GREEN}] Threads      {EKL} {config_state.get('workers', '...')}")
    print(f"{LINE}")


# Main entry point - collects user input and launches automation workers
def run_create():
    config_state = {}

    # Mode selection: HTTP (default) or Browser automation
    print(f" {GREEN}[{RED}01{GREEN}] HTTP Mode {WHITE}(Fast, direct requests)")
    print(f" {GREEN}[{RED}02{GREEN}] FB Auto Create {WHITE}(Playwright, human-like, slower)")
    print(f" {GREEN}[{RED}03{GREEN}] Facebook Automation {WHITE}(Reviews, marketplace & more)")
    print(f" {GREEN}[{RED}04{GREEN}] Outlook Email {WHITE}(Create Outlook/Hotmail accounts)")
    print(f"{LINE}")
    mode_choice = input(f" {GREEN}[{RED}●{GREEN}] Select Mode (1/2/3/4) [1] {EKL} ").strip()
    if mode_choice == "4":
        # Outlook Email Creation mode - WITH proxy support
        # Proxy source priority: proxies.txt (auto) > setting.json > manual prompt
        # Each Outlook account gets the next proxy in rotation (per-context).
        from automation.outlook_register import run_outlook_mode
        config_state["mode"] = "Outlook Email"
        password_config = select_password_config(config_state, lambda: render_config(config_state))
        # Proxy load (checks proxies.txt first inside get_proxy_list)
        proxy_list = get_proxy_list(config_state, lambda: render_config(config_state))
        proxy_cycle = create_proxy_cycle(proxy_list)
        render_config(config_state)
        try:
            _count = int(input(f" {GREEN}[{RED}●{GREEN}] How many Outlook accounts? {WHITE}").strip())
        except Exception:
            _count = 1
        render_config(config_state)
        input(f"\n {WHITE}Press Enter to start Outlook automation... ")
        logo()
        counter = Counter()
        run_outlook_mode(_count, password_config, counter, proxy_list=proxy_list, proxy_cycle=proxy_cycle)
        input(f"\n {WHITE}Press Enter to exit... ")
        return

    if mode_choice == "3":
        # Facebook Automation: reviews, marketplace & more (does not touch mode 1/2)
        from automation.fb_automation import run_reviews_mode
        config_state["mode"] = "Facebook Automation"
        render_config(config_state)
        run_reviews_mode()
        input(f"\n {WHITE}Press Enter to exit... ")
        return

    browser_mode = (mode_choice == "2")
    config_state["mode"] = "Browser (Playwright)" if browser_mode else "HTTP"

    if browser_mode:
        # Setup choice inside FB Auto Create:
        # 1 = Browser Setup (the original flow below, untouched).
        # 2 = Android Setup (Facebook Lite app) - separate module;
        #     selecting it returns from here with its own flow.
        print(f" {GREEN}[{RED}01{GREEN}] Browser Setup {WHITE}(Playwright, PC browser)")
        print(f" {GREEN}[{RED}02{GREEN}] Android Setup {WHITE}(Facebook Lite app - emulator/phone)")
        print(f"{LINE}")
        _setup_choice = input(f" {GREEN}[{RED}●{GREEN}] Select Setup (1/2) [1] {EKL} ").strip()
        if _setup_choice == "2":
            from automation.android_lite_register import run_android_lite_mode
            config_state["mode"] = "FB Auto Create (Android Lite)"
            password_config = select_password_config(config_state, lambda: render_config(config_state))
            render_config(config_state)
            numbers = process_file_input()
            if numbers is None:
                input(f"\n {RED}Press Enter to exit...")
                return
            if not numbers:
                input(f"\n {RED}No numbers found. Press Enter to exit...")
                return
            render_config(config_state)
            input(f"\n {WHITE}Press Enter to start Facebook Lite (Android) automation... ")
            logo()
            counter = Counter()
            run_android_lite_mode(password_config, counter, numbers)
            input(f"\n {WHITE}Press Enter to exit... ")
            return
        # Browser mode: simplified flow (no device/server/proxy needed)
        from automation.browser_register import run_browser_mode
        password_config = select_password_config(config_state, lambda: render_config(config_state))
        render_config(config_state)
        numbers = process_file_input()
        if numbers is None:
            input(f"\n {RED}Press Enter to exit...")
            return
        if not numbers:
            input(f"\n {RED}No numbers found. Press Enter to exit...")
            return
        render_config(config_state)
        input(f"\n {WHITE}Press Enter to start browser automation... ")
        logo()
        counter = Counter()
        run_browser_mode(numbers, password_config, counter)
        input(f"\n {WHITE}Press Enter to exit... ")
        return

    device_type = select_device(config_state, lambda: render_config(config_state))
    browser_type = select_browser(device_type, config_state, lambda: render_config(config_state))
    server = select_server(config_state, lambda: render_config(config_state))
    password_config = select_password_config(config_state, lambda: render_config(config_state))
    proxy_list = get_proxy_list(config_state, lambda: render_config(config_state))
    proxy_cycle = create_proxy_cycle(proxy_list)
    no_proxy_data = get_no_proxy_data()
    config_state["workers"] = "Sequential (1)"

    render_config(config_state)

    numbers = process_file_input()
    if numbers is None:
        input(f"\n {RED}Press Enter to exit...")
        return
    if not numbers:
        input(f"\n {RED}No numbers found. Press Enter to exit...")
        return

    render_config(config_state)
    input(f"\n {WHITE}Press Enter to start automation... ")

    logo()
    counter = Counter()

    config = {
        "device_type": device_type,
        "browser_type": browser_type,
        "server": server,
        "password_config": password_config,
    }

    wid_gen = count(1)

    from automation.create_task import create_worker
    try:
        for num in numbers:
            proxy_data = next(proxy_cycle) if proxy_cycle else no_proxy_data
            wid = next(wid_gen)
            create_worker(wid, num, proxy_data, config, counter)
    except KeyboardInterrupt:
        print(f"\n\n {RED}Stopped by user.")

    # Print final summary
    with print_lock:
        sys.stdout.write('\r' + ' ' * 80 + '\r')
        sys.stdout.flush()

        s = counter.summary()
        print(f"{LINE}")
        print(f" {GREEN}[{RED}●{GREEN}] {WHITE}Completed: {s['checked']} Numbers (Auto Create)")
        print(f" {GREEN}[{RED}●{GREEN}] {GREEN}Success: {s['success']}")
        print(f" {GREEN}[{RED}●{GREEN}] {YELLOW}Failed: {s['failed']}")
        print(f" {GREEN}[{RED}●{GREEN}] {RED}Error: {s['error']}")
        print(f" {GREEN}[{RED}●{GREEN}] {WHITE}No Account: {s['no_account']}")
        print(f"{LINE}")
        print(f" {GREEN}[{RED}●{GREEN}] {CYAN}Output Saved To: {get_output_dir()}")
        print(f"{LINE}")

    input(f"\n {WHITE}Press Enter to exit...")


if __name__ == '__main__':
    try:
        run_create()
    except KeyboardInterrupt:
        print(f"\n {RED}Cancelled.")
        sys.exit(0)
